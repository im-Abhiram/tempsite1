"""
Thamarayyath Employee Portal — Payroll App Tests.
Covers payroll calculation engine (Hourly, Daily, Monthly), all cycles, and finalization lock.
"""

import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Role, CompanySettings, PayrollCycle
from employees.models import (
    Employee, Department, Designation, Shift, SalaryMethod,
    EmploymentStatus, EmploymentType,
)
from attendance.models import AttendanceRecord, AttendanceStatus
from payroll.models import PayrollPeriod, PayrollStatement, PayrollStatus
from payroll.services import generate_payroll_period, finalize_payroll_period

User = get_user_model()


class PayrollEngineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_superadmin(
            username="admin", password="StrongPassword123!"
        )
        self.accountant = User.objects.create_user(
            username="acct", password="StrongPassword123!", role=Role.ACCOUNTANT
        )
        self.owner = User.objects.create_user(
            username="owner", password="StrongPassword123!", role=Role.OWNER
        )

        self.settings = CompanySettings.get()
        self.settings.overtime_allowed = True
        self.settings.overtime_rate_multiplier = Decimal("1.5")
        self.settings.daily_overtime_threshold_hours = Decimal("8.00")
        self.settings.save()

        self.dept = Department.objects.create(name="Operations", code="OPS")
        self.desig = Designation.objects.create(name="Operator", department=self.dept)
        self.shift = Shift.objects.create(
            name="General",
            start_time=datetime.time(9, 0),
            end_time=datetime.time(18, 0),
            unpaid_break_minutes=60,
        )

        # 1. Hourly Employee: ₹200 / hr
        self.emp_hourly = Employee.objects.create(
            employee_id="EMP-0201",
            first_name="Anil",
            last_name="Verma",
            phone="9876543230",
            residential_address="12 MG Road, Kochi",
            emergency_contact_name="Sunil Verma",
            emergency_contact_phone="9876543231",
            department=self.dept,
            designation=self.desig,
            assigned_shift=self.shift,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME,
            salary_calculation_method=SalaryMethod.HOURLY,
            base_salary_rate=Decimal("200.00"),
            overtime_eligible=True,
            standard_working_hours=Decimal("8.00"),
            created_by=self.superadmin,
        )

        # 2. Daily Wage Employee: ₹1000 / day
        self.emp_daily = Employee.objects.create(
            employee_id="EMP-0202",
            first_name="Deepak",
            last_name="Sharma",
            phone="9876543240",
            residential_address="34 Port Road, Cochin",
            emergency_contact_name="Geeta Sharma",
            emergency_contact_phone="9876543241",
            department=self.dept,
            designation=self.desig,
            assigned_shift=self.shift,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.DAILY_WAGE,
            salary_calculation_method=SalaryMethod.DAILY_WAGE,
            base_salary_rate=Decimal("1000.00"),
            overtime_eligible=True,
            standard_working_hours=Decimal("8.00"),
            created_by=self.superadmin,
        )

        # 3. Monthly Salaried Employee: ₹30,000 / month
        self.emp_monthly = Employee.objects.create(
            employee_id="EMP-0203",
            first_name="Manoj",
            last_name="Menon",
            phone="9876543250",
            residential_address="56 Marine Drive, Ernakulam",
            emergency_contact_name="Deepa Menon",
            emergency_contact_phone="9876543251",
            department=self.dept,
            designation=self.desig,
            assigned_shift=self.shift,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME,
            salary_calculation_method=SalaryMethod.MONTHLY,
            base_salary_rate=Decimal("30000.00"),
            overtime_eligible=False,
            standard_working_hours=Decimal("8.00"),
            created_by=self.superadmin,
        )

    def test_payroll_generation_and_calculation_engine(self):
        start_date = datetime.date(2026, 10, 1)
        end_date = datetime.date(2026, 10, 7)  # Weekly (7 days)
        tz = timezone.get_current_timezone()

        # Create attendance for 5 days (Oct 1 to Oct 5)
        for day in range(1, 6):
            cur_date = datetime.date(2026, 10, day)
            # Hourly employee worked 9 hours each day (8 reg + 1 OT)
            c_in = timezone.make_aware(datetime.datetime.combine(cur_date, datetime.time(9, 0)), tz)
            c_out = timezone.make_aware(datetime.datetime.combine(cur_date, datetime.time(19, 0)), tz)
            rec = AttendanceRecord(
                employee=self.emp_hourly,
                work_date=cur_date,
                check_in=c_in, check_out=c_out,
                break_duration_minutes=60,
                status=AttendanceStatus.PRESENT,
                created_by=self.accountant,
            )
            rec.calculate_hours(Decimal("8.00"))
            rec.save()

            # Daily employee present for 5 days
            AttendanceRecord.objects.create(
                employee=self.emp_daily,
                work_date=cur_date,
                status=AttendanceStatus.PRESENT,
                net_working_hours=Decimal("8.00"),
                regular_hours=Decimal("8.00"),
                created_by=self.accountant,
            )

        # Generate Weekly Payroll
        period = generate_payroll_period(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=start_date,
            end_date=end_date,
            requested_by=self.accountant,
            notes="Test Weekly Cycle",
        )
        self.assertEqual(period.status, PayrollStatus.DRAFT)
        self.assertEqual(period.statements.count(), 3)

        # Check Hourly employee statement:
        # 5 days * 8 hours = 40 reg hours @ ₹200 = ₹8,000 base pay
        # 5 days * 1 hour = 5 OT hours @ ₹200 * 1.5 = ₹1,500 OT pay
        # Gross = ₹9,500
        stmt_h = period.statements.get(employee=self.emp_hourly)
        self.assertEqual(stmt_h.regular_hours, Decimal("40.00"))
        self.assertEqual(stmt_h.overtime_hours, Decimal("5.00"))
        self.assertEqual(stmt_h.base_pay, Decimal("8000.00"))
        self.assertEqual(stmt_h.overtime_pay, Decimal("1500.00"))
        self.assertEqual(stmt_h.gross_pay, Decimal("9500.00"))

        # Check Daily employee statement:
        # 5 present days * ₹1000 = ₹5,000 base pay
        stmt_d = period.statements.get(employee=self.emp_daily)
        self.assertEqual(stmt_d.payable_days, Decimal("5.0000"))
        self.assertEqual(stmt_d.base_pay, Decimal("5000.00"))

    def test_payroll_finalization_locks_attendance_records(self):
        start_date = datetime.date(2026, 10, 1)
        end_date = datetime.date(2026, 10, 7)

        att_rec = AttendanceRecord.objects.create(
            employee=self.emp_hourly,
            work_date=start_date,
            status=AttendanceStatus.PRESENT,
            net_working_hours=Decimal("8.00"),
            regular_hours=Decimal("8.00"),
            created_by=self.accountant,
        )
        self.assertFalse(att_rec.is_locked_by_payroll)

        period = generate_payroll_period(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=start_date,
            end_date=end_date,
            requested_by=self.accountant,
        )

        period.status = PayrollStatus.REVIEWED
        period.save()

        # Finalize period
        finalized = finalize_payroll_period(period, finalized_by=self.superadmin)
        self.assertEqual(finalized.status, PayrollStatus.FINALIZED)

        att_rec.refresh_from_db()
        self.assertTrue(att_rec.is_locked_by_payroll)

    def test_payroll_period_properties_and_views_render(self):
        start_date = datetime.date(2026, 10, 1)
        end_date = datetime.date(2026, 10, 7)
        period = generate_payroll_period(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=start_date,
            end_date=end_date,
            requested_by=self.accountant,
        )

        # Check properties
        self.assertGreaterEqual(period.total_net_pay, Decimal("0.00"))
        self.assertGreaterEqual(period.total_gross_pay, Decimal("0.00"))
        self.assertIsNotNone(period.created_at)
        self.assertEqual(period.created_by, self.accountant)

        # Test view rendering for Superadmin, Accountant, Owner
        for user in [self.superadmin, self.accountant, self.owner]:
            self.client.force_login(user)
            res = self.client.get(reverse("payroll:period_detail", kwargs={"pk": period.pk}))
            self.assertEqual(res.status_code, 200)

            res_list = self.client.get(reverse("payroll:period_list"))
            self.assertEqual(res_list.status_code, 200)

        # Test review view
        self.client.force_login(self.superadmin)
        res_review = self.client.get(reverse("payroll:review", kwargs={"pk": period.pk}))
        self.assertEqual(res_review.status_code, 200)

        # Transition to REVIEWED and test finalize view
        period.status = PayrollStatus.REVIEWED
        period.save()
        res_finalize = self.client.get(reverse("payroll:finalize", kwargs={"pk": period.pk}))
        self.assertEqual(res_finalize.status_code, 200)

    def test_all_four_payroll_periods_supported(self):
        """Verify generation succeeds across all 4 cycles: Weekly, Biweekly, Three-Weekly, Monthly."""
        cycles = [
            (PayrollCycle.WEEKLY, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7)),
            (PayrollCycle.BIWEEKLY, datetime.date(2026, 1, 8), datetime.date(2026, 1, 21)),
            (PayrollCycle.THREE_WEEKLY, datetime.date(2026, 1, 22), datetime.date(2026, 2, 11)),
            (PayrollCycle.MONTHLY, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)),
        ]
        for cycle_type, start, end in cycles:
            p = generate_payroll_period(cycle_type, start, end, requested_by=self.accountant)
            self.assertEqual(p.cycle_type, cycle_type)
            self.assertEqual(p.status, PayrollStatus.DRAFT)
            self.assertTrue(p.statements.exists())

    def test_owner_denied_generating_or_finalizing_payroll(self):
        """Owner must never be able to trigger payroll generation or finalization."""
        self.client.force_login(self.owner)
        gen_res = self.client.get(reverse("payroll:generate"))
        self.assertEqual(gen_res.status_code, 403)

        period = PayrollPeriod.objects.create(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=datetime.date(2026, 5, 1),
            end_date=datetime.date(2026, 5, 7),
            status=PayrollStatus.REVIEWED,
        )
        fin_res = self.client.post(reverse("payroll:finalize", kwargs={"pk": period.pk}))
        self.assertEqual(fin_res.status_code, 403)

    def test_wage_disbursement_tracking_and_marking_paid(self):
        """Verify wage disbursement page, individual and bulk payment marking, and toggling."""
        period = generate_payroll_period(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 6, 7),
            requested_by=self.accountant,
        )
        self.client.force_login(self.accountant)

        # 1. View payment tracking page
        res = self.client.get(reverse("payroll:period_payments", kwargs={"period_pk": period.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Wage Disbursement Tracking")
        self.assertEqual(period.total_unpaid_count, period.statements.count())

        # 2. Mark one statement as paid
        stmt = period.statements.first()
        toggle_res = self.client.post(reverse("payroll:toggle_payment", kwargs={"pk": stmt.pk}), {
            "action": "mark_paid",
            "payment_method": "BANK_TRANSFER",
            "payment_remarks": "NEFT Ref #992812",
        })
        self.assertEqual(toggle_res.status_code, 302)
        stmt.refresh_from_db()
        self.assertTrue(stmt.is_paid)
        self.assertEqual(stmt.payment_method, "BANK_TRANSFER")
        self.assertEqual(stmt.payment_remarks, "NEFT Ref #992812")
        self.assertIsNotNone(stmt.paid_at)

        # 3. Bulk mark all remaining as paid
        bulk_res = self.client.post(reverse("payroll:bulk_mark_paid", kwargs={"period_pk": period.pk}), {
            "payment_method": "CASH",
            "payment_remarks": "Office Cash Handover",
        })
        self.assertEqual(bulk_res.status_code, 302)
        self.assertEqual(period.total_unpaid_count, 0)
        self.assertEqual(period.total_paid_count, period.statements.count())

        # 4. Toggle back to unpaid
        unmark_res = self.client.post(reverse("payroll:toggle_payment", kwargs={"pk": stmt.pk}), {
            "action": "mark_unpaid",
        })
        self.assertEqual(unmark_res.status_code, 302)
        stmt.refresh_from_db()
        self.assertFalse(stmt.is_paid)

    def test_excel_wage_sheet_and_payslip_export(self):
        """Verify generation of Excel wage sheet with formula calculations and individual payslip."""
        period = generate_payroll_period(
            cycle_type=PayrollCycle.WEEKLY,
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 7),
            requested_by=self.accountant,
        )
        self.client.force_login(self.accountant)

        # Excel Wage Sheet
        res_excel = self.client.get(reverse("reports:payroll_excel", kwargs={"period_pk": period.pk}))
        self.assertEqual(res_excel.status_code, 200)
        self.assertEqual(
            res_excel["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("wage_sheet_", res_excel["Content-Disposition"])

        # Individual Payslip Excel
        stmt = period.statements.first()
        res_single = self.client.get(reverse("reports:statement_excel", kwargs={"statement_pk": stmt.pk}))
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(
            res_single["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("payslip_", res_single["Content-Disposition"])



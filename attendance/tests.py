"""
Thamarayyath Employee Portal — Attendance Tests.
Covers working hour arithmetic, overnight shifts, overtime calculation, late detection, and immutable correction logs.
"""

import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Role, CompanySettings
from employees.models import (
    Employee, Department, Designation, Shift, SalaryMethod,
    EmploymentStatus, EmploymentType,
)
from attendance.models import (
    AttendanceRecord, AttendanceStatus, AttendanceEntryMethod,
    AttendanceCorrectionLog,
)

User = get_user_model()


class AttendanceCalculationsAndLockTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_superadmin(
            username="admin", password="StrongPassword123!"
        )
        self.accountant = User.objects.create_user(
            username="acct", password="StrongPassword123!", role=Role.ACCOUNTANT
        )
        self.settings = CompanySettings.get()
        self.settings.daily_overtime_threshold_hours = Decimal("8.00")
        self.settings.late_grace_period_minutes = 15
        self.settings.save()

        self.dept = Department.objects.create(name="Production", code="PROD")
        self.desig = Designation.objects.create(name="Technician", department=self.dept)
        self.shift = Shift.objects.create(
            name="Day Shift",
            start_time=datetime.time(9, 0),
            end_time=datetime.time(18, 0),
            unpaid_break_minutes=60,
        )
        self.night_shift = Shift.objects.create(
            name="Night Shift",
            start_time=datetime.time(22, 0),
            end_time=datetime.time(6, 0),
            unpaid_break_minutes=30,
            is_night_shift=True,
        )

        self.emp = Employee.objects.create(
            employee_id="EMP-0101",
            first_name="Ramesh",
            last_name="Nair",
            phone="9876543220",
            residential_address="45 Market Road, Aluva",
            emergency_contact_name="Priya Nair",
            emergency_contact_phone="9876543221",
            department=self.dept,
            designation=self.desig,
            assigned_shift=self.shift,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME,
            salary_calculation_method=SalaryMethod.HOURLY,
            base_salary_rate=Decimal("150.00"),
            standard_working_hours=Decimal("8.00"),
            created_by=self.superadmin,
        )

    def test_standard_working_hours_and_overtime_calculation(self):
        work_date = datetime.date(2026, 10, 1)
        tz = timezone.get_current_timezone()

        # 08:00 to 19:00 with 60 min break = 11 hours - 1 hour break = 10.00 hours total
        check_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(8, 0)), tz)
        check_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(19, 0)), tz)

        record = AttendanceRecord(
            employee=self.emp,
            work_date=work_date,
            check_in=check_in,
            check_out=check_out,
            break_duration_minutes=60,
            status=AttendanceStatus.PRESENT,
            created_by=self.accountant,
        )
        record.calculate_hours(daily_threshold_hours=Decimal("8.00"))
        record.save()

        self.assertEqual(record.net_working_hours, Decimal("10.00"))
        self.assertEqual(record.regular_hours, Decimal("8.00"))
        self.assertEqual(record.overtime_hours, Decimal("2.00"))

    def test_overnight_shift_calculation(self):
        work_date = datetime.date(2026, 10, 2)
        tz = timezone.get_current_timezone()

        # Check in 22:00 on Oct 2, Check out 06:00 on Oct 3, 30 min break
        # Duration: 8 hours - 0.5 break = 7.50 hours
        check_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(22, 0)), tz)
        check_out = timezone.make_aware(datetime.datetime.combine(work_date + datetime.timedelta(days=1), datetime.time(6, 0)), tz)

        record = AttendanceRecord(
            employee=self.emp,
            work_date=work_date,
            check_in=check_in,
            check_out=check_out,
            break_duration_minutes=30,
            status=AttendanceStatus.PRESENT,
            created_by=self.accountant,
        )
        record.calculate_hours(daily_threshold_hours=Decimal("8.00"))
        record.save()

        self.assertEqual(record.net_working_hours, Decimal("7.50"))
        self.assertEqual(record.overtime_hours, Decimal("0.00"))

    def test_late_arrival_detection_with_grace_period(self):
        work_date = datetime.date(2026, 10, 3)
        tz = timezone.get_current_timezone()

        # Shift starts 09:00. Grace period 15 min (until 09:15).
        # Check-in at 09:25 is 25 minutes late.
        check_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(9, 25)), tz)
        check_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(18, 0)), tz)

        record = AttendanceRecord(
            employee=self.emp,
            work_date=work_date,
            check_in=check_in,
            check_out=check_out,
            break_duration_minutes=60,
            status=AttendanceStatus.PRESENT,
            created_by=self.accountant,
        )
        record.calculate_late_flag(grace_period_minutes=15)
        record.save()

        self.assertTrue(record.is_late)
        self.assertEqual(record.late_by_minutes, 25)

    def test_attendance_correction_requires_reason_and_creates_log(self):
        work_date = datetime.date(2026, 10, 4)
        tz = timezone.get_current_timezone()
        check_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(9, 0)), tz)
        check_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(18, 0)), tz)

        record = AttendanceRecord.objects.create(
            employee=self.emp,
            work_date=work_date,
            check_in=check_in,
            check_out=check_out,
            break_duration_minutes=60,
            status=AttendanceStatus.PRESENT,
            created_by=self.accountant,
        )

        self.client.force_login(self.accountant)
        response = self.client.post(reverse("attendance:attendance_correct", args=[record.pk]), {
            "check_in_time": "09:00",
            "check_out_time": "19:00",
            "break_duration_minutes": 60,
            "status": AttendanceStatus.PRESENT,
            "correction_reason": "Employee worked 1 hour extra approved overtime.",
        })
        self.assertRedirects(response, reverse("attendance:attendance_detail", args=[record.pk]))

        # Verify AttendanceCorrectionLog was created
        log = AttendanceCorrectionLog.objects.filter(attendance_record=record).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.modified_by, self.accountant)
        self.assertIn("approved overtime", log.reason)

    def test_payroll_lock_prevents_routine_correction(self):
        work_date = datetime.date(2026, 10, 5)
        record = AttendanceRecord.objects.create(
            employee=self.emp,
            work_date=work_date,
            break_duration_minutes=60,
            status=AttendanceStatus.PRESENT,
            is_locked_by_payroll=True,  # Locked by payroll
            created_by=self.accountant,
        )

        self.client.force_login(self.accountant)
        # Attempt to post correction
        res = self.client.post(reverse("attendance:attendance_correct", args=[record.pk]), {
            "status": AttendanceStatus.PRESENT,
            "break_duration_minutes": 60,
            "correction_reason": "Attempting modification on locked period.",
        })
        # View returns 403 PermissionDenied when record is locked
        self.assertEqual(res.status_code, 403)

    def test_quick_attendance_mark_single_button(self):
        self.client.force_login(self.accountant)
        work_date = datetime.date(2026, 10, 20)

        # 1-Click Mark Present
        res = self.client.post(reverse("attendance:quick_mark"), {
            "employee_pk": self.emp.pk,
            "work_date": str(work_date),
            "action_type": "mark_present",
        })
        self.assertEqual(res.status_code, 302)

        rec = AttendanceRecord.objects.get(employee=self.emp, work_date=work_date)
        self.assertEqual(rec.status, AttendanceStatus.PRESENT)
        self.assertGreater(rec.net_working_hours, Decimal("0.0000"))

    def test_manual_attendance_log_with_custom_overtime_and_remarks(self):
        self.client.force_login(self.accountant)
        work_date = datetime.date(2026, 10, 22)

        res = self.client.post(reverse("attendance:attendance_mark_emp", args=[self.emp.pk]), {
            "employee_pk": self.emp.pk,
            "work_date": str(work_date),
            "status": AttendanceStatus.PRESENT,
            "check_in_time": "09:00",
            "check_out_time": "18:00",
            "break_duration_minutes": 60,
            "overtime_hours": "3.50",
            "correction_reason": "Approved 3.5 hrs overtime for emergency server upgrade",
        })
        self.assertEqual(res.status_code, 302)

        rec = AttendanceRecord.objects.get(employee=self.emp, work_date=work_date)
        self.assertEqual(rec.overtime_hours, Decimal("3.5000"))
        self.assertEqual(rec.correction_reason, "Approved 3.5 hrs overtime for emergency server upgrade")

    def test_holiday_create_and_delete(self):
        from attendance.models import Holiday
        self.client.force_login(self.accountant)

        # Add holiday
        add_res = self.client.post(reverse("attendance:holiday_create"), {
            "name": "Diwali Festival",
            "date": "2026-11-12",
            "is_paid": True,
        })
        self.assertRedirects(add_res, reverse("attendance:holiday_list"))
        holiday = Holiday.objects.get(name="Diwali Festival")
        self.assertEqual(str(holiday.date), "2026-11-12")

        # Delete holiday
        del_res = self.client.post(reverse("attendance:holiday_delete", args=[holiday.pk]))
        self.assertRedirects(del_res, reverse("attendance:holiday_list"))
        self.assertFalse(Holiday.objects.filter(pk=holiday.pk).exists())

    def test_duplicate_attendance_prevented(self):
        """Cannot insert duplicate attendance for the same employee and same date."""
        work_date = datetime.date(2026, 4, 15)
        AttendanceRecord.objects.create(
            employee=self.emp,
            work_date=work_date,
            status=AttendanceStatus.PRESENT,
        )

        self.client.force_login(self.accountant)
        dup_res = self.client.post(reverse("attendance:attendance_mark_emp", args=[self.emp.pk]), {
            "employee_pk": self.emp.pk,
            "work_date": str(work_date),
            "status": AttendanceStatus.PRESENT,
            "check_in_time": "09:00",
            "break_duration_minutes": 60,
        })
        self.assertEqual(dup_res.status_code, 200)
        self.assertContains(dup_res, "Attendance already exists for EMP-0101")

    def test_leave_record_creation_and_workflow(self):
        from attendance.models import LeaveRecord, LeaveType, LeaveStatus
        self.client.force_login(self.accountant)

        res = self.client.post(reverse("attendance:leave_create"), {
            "employee": self.emp.pk,
            "leave_type": LeaveType.CASUAL_LEAVE,
            "start_date": "2026-05-10",
            "end_date": "2026-05-12",
            "reason": "Personal family function in Kozhikode",
            "status": LeaveStatus.APPROVED,
        })
        self.assertRedirects(res, reverse("attendance:leave_list"))

        leave = LeaveRecord.objects.get(employee=self.emp, start_date="2026-05-10")
        self.assertEqual(leave.duration_days, 3)
        self.assertEqual(leave.approved_by, self.accountant)



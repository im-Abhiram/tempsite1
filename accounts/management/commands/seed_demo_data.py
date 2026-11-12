"""
Thamarayyath Employee Portal — Management Command: seed_demo_data

Populates the database with realistic demonstration data for development,
deployment verification, and testing.

Creates:
- System users (Superadmin, Accountant, Owner)
- Company settings
- Departments, Designations, and Shifts
- Employees with all 3 salary methods (Monthly, Daily, Hourly)
- Paid holidays
- 10+ days of attendance records (on-time, late, overnight)
- Finalized and draft payroll periods

Usage:
    python manage.py seed_demo_data
"""

import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Role, CompanySettings, PayrollCycle
from employees.models import (
    Department, Designation, Shift, Employee, SalaryRateHistory,
    SalaryMethod, EmploymentStatus, EmploymentType,
)
from attendance.models import AttendanceRecord, AttendanceStatus, AttendanceEntryMethod, Holiday
from payroll.models import PayrollPeriod, PayrollStatement, PayrollStatus
from payroll.services import generate_payroll_period, finalize_payroll_period

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds database with comprehensive demo data for Thamarayyath Employee Portal."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Thamarayyath Employee Portal with demonstration data..."))

        # 1. Company Settings
        settings = CompanySettings.get()
        settings.company_name = "Thamarayyath"
        settings.currency_symbol = "₹"
        settings.timezone = "Asia/Kolkata"
        settings.standard_daily_hours = Decimal("8.00")
        settings.standard_weekly_hours = Decimal("40.00")
        settings.overtime_allowed = True
        settings.overtime_rate_multiplier = Decimal("1.5")
        settings.daily_overtime_threshold_hours = Decimal("8.00")
        settings.late_grace_period_minutes = 15
        settings.default_unpaid_break_minutes = 60
        settings.payroll_cycle = PayrollCycle.MONTHLY
        settings.payroll_start_day = 1
        settings.allow_owner_export = True
        settings.save()
        self.stdout.write(self.style.SUCCESS("[OK] Company settings configured."))

        # 2. Users
        superadmin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "role": Role.SUPERADMIN,
                "display_name": "Portal Superadmin",
                "designation": "Superadmin",
                "email": "admin@thamarayyath.local",
            }
        )
        superadmin.designation = "Superadmin"
        superadmin.set_password("AdminPass123!")
        superadmin.save()

        accountant, _ = User.objects.get_or_create(
            username="accountant",
            defaults={
                "role": Role.OFFICE_ADMIN,
                "display_name": "Office Administrator",
                "designation": "Office Administrator",
                "email": "accountant@thamarayyath.local",
            }
        )
        accountant.role = Role.OFFICE_ADMIN
        accountant.display_name = "Office Administrator"
        accountant.designation = "Office Administrator"
        accountant.set_password("AccountPass123!")
        accountant.save()

        owner, _ = User.objects.get_or_create(
            username="owner",
            defaults={
                "role": Role.OWNER,
                "display_name": "Company Managing Director",
                "designation": "Managing Director",
                "email": "owner@thamarayyath.local",
            }
        )
        owner.designation = "Managing Director"
        owner.set_password("OwnerPass123!")
        owner.save()
        self.stdout.write(self.style.SUCCESS("[OK] Demo users created (admin, accountant, owner)."))

        # 3. Departments & Designations
        dept_eng, _ = Department.objects.get_or_create(name="Engineering & IT", code="ENG")
        dept_ops, _ = Department.objects.get_or_create(name="Operations & Production", code="OPS")
        dept_qc, _ = Department.objects.get_or_create(name="Quality Assurance", code="QA")
        dept_hr, _ = Department.objects.get_or_create(name="Human Resources & Admin", code="HR")

        desig_se, _ = Designation.objects.get_or_create(name="Senior Software Engineer", department=dept_eng)
        desig_dev, _ = Designation.objects.get_or_create(name="Junior Systems Engineer", department=dept_eng)
        desig_sup, _ = Designation.objects.get_or_create(name="Production Supervisor", department=dept_ops)
        desig_op, _ = Designation.objects.get_or_create(name="Machinery Operator", department=dept_ops)
        desig_qa, _ = Designation.objects.get_or_create(name="Quality Inspector", department=dept_qc)
        desig_hr, _ = Designation.objects.get_or_create(name="HR Operations Executive", department=dept_hr)
        self.stdout.write(self.style.SUCCESS("[OK] Departments and Designations created."))

        # 4. Shifts
        shift_morning, _ = Shift.objects.get_or_create(
            name="General Morning Shift",
            defaults={
                "start_time": datetime.time(9, 0),
                "end_time": datetime.time(18, 0),
                "unpaid_break_minutes": 60,
                "is_night_shift": False,
            }
        )
        shift_evening, _ = Shift.objects.get_or_create(
            name="Afternoon Shift",
            defaults={
                "start_time": datetime.time(14, 0),
                "end_time": datetime.time(22, 0),
                "unpaid_break_minutes": 45,
                "is_night_shift": False,
            }
        )
        shift_night, _ = Shift.objects.get_or_create(
            name="Overnight Production Shift",
            defaults={
                "start_time": datetime.time(22, 0),
                "end_time": datetime.time(6, 0),
                "unpaid_break_minutes": 30,
                "is_night_shift": True,
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Work shifts created (Day, Evening, Overnight)."))

        # 5. Employees
        employees_data = [
            {
                "id": "EMP-0001",
                "first": "Abhiram", "last": "Thamarayyath",
                "phone": "+91 98470 11223", "email": "abhiram@thamarayyath.local",
                "dept": dept_eng, "desig": desig_se, "shift": shift_morning,
                "joining": datetime.date(2023, 1, 15),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.FULL_TIME,
                "method": SalaryMethod.MONTHLY, "rate": Decimal("65000.00"), "ot": False,
            },
            {
                "id": "EMP-0002",
                "first": "Ramesh", "last": "Nair",
                "phone": "+91 98471 22334", "email": "ramesh.nair@thamarayyath.local",
                "dept": dept_ops, "desig": desig_sup, "shift": shift_morning,
                "joining": datetime.date(2023, 6, 1),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.FULL_TIME,
                "method": SalaryMethod.MONTHLY, "rate": Decimal("48000.00"), "ot": True,
            },
            {
                "id": "EMP-0003",
                "first": "Kavitha", "last": "Pillai",
                "phone": "+91 98472 33445", "email": "kavitha.p@thamarayyath.local",
                "dept": dept_qc, "desig": desig_qa, "shift": shift_evening,
                "joining": datetime.date(2024, 2, 10),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.FULL_TIME,
                "method": SalaryMethod.MONTHLY, "rate": Decimal("38000.00"), "ot": False,
            },
            {
                "id": "EMP-0004",
                "first": "Manoj", "last": "Menon",
                "phone": "+91 98473 44556", "email": "manoj.m@thamarayyath.local",
                "dept": dept_ops, "desig": desig_op, "shift": shift_night,
                "joining": datetime.date(2024, 4, 1),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.DAILY_WAGE,
                "method": SalaryMethod.DAILY_WAGE, "rate": Decimal("1100.00"), "ot": True,
            },
            {
                "id": "EMP-0005",
                "first": "Sunil", "last": "Kumar",
                "phone": "+91 98474 55667", "email": "sunil.k@thamarayyath.local",
                "dept": dept_ops, "desig": desig_op, "shift": shift_morning,
                "joining": datetime.date(2024, 8, 15),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.CONTRACT,
                "method": SalaryMethod.HOURLY, "rate": Decimal("220.00"), "ot": True,
            },
            {
                "id": "EMP-0006",
                "first": "Anjali", "last": "Devi",
                "phone": "+91 98475 66778", "email": "anjali.d@thamarayyath.local",
                "dept": dept_hr, "desig": desig_hr, "shift": shift_morning,
                "joining": datetime.date(2024, 10, 1),
                "status": EmploymentStatus.ACTIVE, "type": EmploymentType.FULL_TIME,
                "method": SalaryMethod.MONTHLY, "rate": Decimal("32000.00"), "ot": False,
            },
        ]

        created_employees = []
        for ed in employees_data:
            emp, created = Employee.objects.get_or_create(
                employee_id=ed["id"],
                defaults={
                    "first_name": ed["first"],
                    "last_name": ed["last"],
                    "phone": ed["phone"],
                    "email": ed["email"],
                    "residential_address": f"{ed['last']} House, Ernakulam, Kerala",
                    "emergency_contact_name": f"Next of Kin of {ed['first']}",
                    "emergency_contact_phone": "+91 98470 00000",
                    "department": ed["dept"],
                    "designation": ed["desig"],
                    "assigned_shift": ed["shift"],
                    "date_of_joining": ed["joining"],
                    "employment_status": ed["status"],
                    "employment_type": ed["type"],
                    "salary_calculation_method": ed["method"],
                    "base_salary_rate": ed["rate"],
                    "overtime_eligible": ed["ot"],
                    "standard_working_hours": Decimal("8.00"),
                    "created_by": superadmin,
                }
            )
            if created:
                SalaryRateHistory.objects.create(
                    employee=emp,
                    effective_date=emp.date_of_joining,
                    salary_calculation_method=emp.salary_calculation_method,
                    base_rate=emp.base_salary_rate,
                    changed_by=superadmin,
                    reason="Initial employment onboarding record.",
                )
            created_employees.append(emp)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(created_employees)} employees created across Monthly, Daily, and Hourly wage structures."))

        # 6. Paid Holidays
        current_year = timezone.now().year
        holidays_data = [
            ("Republic Day", datetime.date(current_year, 1, 26), True),
            ("May Day", datetime.date(current_year, 5, 1), True),
            ("Independence Day", datetime.date(current_year, 8, 15), True),
            ("Gandhi Jayanti", datetime.date(current_year, 10, 2), True),
            ("Kerala Piravi", datetime.date(current_year, 11, 1), True),
        ]
        for name, h_date, paid in holidays_data:
            Holiday.objects.get_or_create(date=h_date, defaults={"name": name, "is_paid": paid, "created_by": superadmin})
        self.stdout.write(self.style.SUCCESS("[OK] Statutory holidays registered."))

        # 7. Attendance Records (Past 10 days)
        today = timezone.localdate()
        tz = timezone.get_current_timezone()

        for day_offset in range(10, 0, -1):
            work_date = today - datetime.timedelta(days=day_offset)
            # Skip Sunday (day 6)
            if work_date.weekday() == 6:
                continue

            for idx, emp in enumerate(created_employees):
                if AttendanceRecord.objects.filter(employee=emp, work_date=work_date).exists():
                    continue

                # Varied realistic attendance patterns
                is_overnight = (emp.assigned_shift and emp.assigned_shift.is_night_shift)
                if is_overnight:
                    c_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(22, 0)), tz)
                    c_out = timezone.make_aware(datetime.datetime.combine(work_date + datetime.timedelta(days=1), datetime.time(6, 0)), tz)
                    status = AttendanceStatus.PRESENT
                    break_mins = 30
                elif idx == 1 and day_offset == 3:
                    # Ramesh was late one day (09:25 clock-in)
                    c_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(9, 25)), tz)
                    c_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(19, 0)), tz)  # Overtime
                    status = AttendanceStatus.PRESENT
                    break_mins = 60
                elif idx == 4 and day_offset == 2:
                    # Sunil had overtime (09:00 to 20:00)
                    c_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(9, 0)), tz)
                    c_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(20, 0)), tz)  # 2 hrs OT
                    status = AttendanceStatus.PRESENT
                    break_mins = 60
                else:
                    c_in = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(9, 0)), tz)
                    c_out = timezone.make_aware(datetime.datetime.combine(work_date, datetime.time(18, 0)), tz)
                    status = AttendanceStatus.PRESENT
                    break_mins = 60

                rec = AttendanceRecord(
                    employee=emp,
                    work_date=work_date,
                    check_in=c_in,
                    check_out=c_out,
                    break_duration_minutes=break_mins,
                    status=status,
                    entry_method=AttendanceEntryMethod.MANUAL,
                    created_by=accountant,
                )
                rec.calculate_hours(settings.daily_overtime_threshold_hours)
                rec.calculate_late_flag(settings.late_grace_period_minutes)
                rec.save()

        self.stdout.write(self.style.SUCCESS("[OK] Attendance records populated with on-time, late, and overtime samples."))

        self.stdout.write(self.style.SUCCESS("""
======================================================================
  THAMARAYYATH EMPLOYEE PORTAL -- READY!
======================================================================
  Default System Accounts:
  ------------------------------------------------------------------
  * Superadmin:            admin      /  AdminPass123!
  * Office Administration: accountant /  AccountPass123!
  * Owner:                 owner      /  OwnerPass123!
======================================================================
"""))

"""
Thamarayyath Employee Portal — Reports Tests.
Tests CSV exports, role access restrictions, and formula injection sanitization.
"""

from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Role, CompanySettings, PayrollCycle
from employees.models import Employee, Department, Designation, SalaryMethod, EmploymentStatus, EmploymentType
from attendance.models import AttendanceRecord, AttendanceStatus
from payroll.models import PayrollPeriod, PayrollStatement, PayrollStatus
from reports.views import SAFE_STR

User = get_user_model()


class ReportsSecurityAndExportTests(TestCase):
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
        self.settings.allow_owner_export = False
        self.settings.save()

        self.dept = Department.objects.create(name="Quality", code="QA")
        self.desig = Designation.objects.create(name="Inspector", department=self.dept)

        self.emp = Employee.objects.create(
            employee_id="EMP-9001",
            first_name="=HYPERLINK('http://malicious.com')",
            last_name="TestUser",
            phone="9876543299",
            residential_address="Test Address",
            emergency_contact_name="Contact",
            emergency_contact_phone="9876543298",
            department=self.dept,
            designation=self.desig,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME,
            salary_calculation_method=SalaryMethod.MONTHLY,
            base_salary_rate=Decimal("40000.00"),
        )

    def test_formula_injection_guard(self):
        """Formula characters (=, +, -, @) must be escaped to prevent spreadsheet execution."""
        unsafe_val = "=cmd|'/C calc'!A0"
        sanitized = SAFE_STR(unsafe_val)
        self.assertTrue(sanitized.startswith("'"))

        normal_val = "Regular Name"
        self.assertEqual(SAFE_STR(normal_val), "Regular Name")

    def test_employee_list_csv_export_as_accountant(self):
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("reports:employees_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        content = response.content.decode("utf-8")
        self.assertIn("EMP-9001", content)
        # Verify malicious payload was escaped with leading single-quote
        self.assertIn("'=HYPERLINK", content)

    def test_owner_export_denied_when_disabled(self):
        """When allow_owner_export is False, Owner must receive 403 PermissionDenied."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("reports:employees_csv"))
        self.assertEqual(response.status_code, 403)

    def test_owner_export_allowed_when_enabled_by_settings(self):
        """When allow_owner_export is True, Owner can download non-sensitive reports."""
        self.settings.allow_owner_export = True
        self.settings.save()

        self.client.force_login(self.owner)
        response = self.client.get(reverse("reports:employees_csv"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        # Owner receives restricted salary placeholder in employee CSV
        self.assertIn("RESTRICTED", content)

    def test_payroll_cycle_csv_export_owner_always_denied(self):
        """Owner cannot access detailed payroll cycle CSV regardless of general export setting."""
        self.settings.allow_owner_export = True
        self.settings.save()

        self.client.force_login(self.owner)
        response = self.client.get(reverse("reports:payroll_cycle_csv") + "?cycle=MONTHLY")
        self.assertEqual(response.status_code, 403)

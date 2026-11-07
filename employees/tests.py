"""
Thamarayyath Employee Portal — Employees App Tests.
Covers employee roster, salary rate audit tracking, and private document security.
"""

import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import Role
from employees.models import (
    Employee, Department, Designation, Shift, SalaryRateHistory,
    SalaryMethod, EmploymentStatus, EmploymentType,
)

User = get_user_model()


class EmployeeManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_superadmin(
            username="admin1", password="StrongPassword123!"
        )
        self.accountant = User.objects.create_user(
            username="acct1", password="StrongPassword123!", role=Role.ACCOUNTANT
        )
        self.owner = User.objects.create_user(
            username="owner1", password="StrongPassword123!", role=Role.OWNER
        )

        self.dept = Department.objects.create(name="Engineering", code="ENG")
        self.desig = Designation.objects.create(name="Software Engineer", department=self.dept)
        self.shift = Shift.objects.create(
            name="General Morning",
            start_time=datetime.time(9, 0),
            end_time=datetime.time(18, 0),
            unpaid_break_minutes=60,
        )

        self.employee = Employee.objects.create(
            employee_id="EMP-0001",
            first_name="Abhiram",
            last_name="Kumar",
            phone="9876543210",
            residential_address="123 Tech Park, Ernakulam",
            emergency_contact_name="Sita Kumar",
            emergency_contact_phone="9876543211",
            department=self.dept,
            designation=self.desig,
            assigned_shift=self.shift,
            date_of_joining=datetime.date(2025, 1, 1),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME,
            salary_calculation_method=SalaryMethod.MONTHLY,
            base_salary_rate=Decimal("45000.00"),
            standard_working_hours=Decimal("8.00"),
            created_by=self.superadmin,
        )

    def test_employee_creation_and_fields(self):
        self.assertEqual(self.employee.full_name, "Abhiram Kumar")
        self.assertEqual(self.employee.department.name, "Engineering")
        self.assertEqual(self.employee.designation.name, "Software Engineer")
        self.assertEqual(self.employee.base_salary_rate, Decimal("45000.00"))

    def test_salary_update_creates_history_record(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse("employees:salary_update", args=[self.employee.pk]), {
            "effective_date": "2026-06-01",
            "salary_calculation_method": SalaryMethod.MONTHLY,
            "base_rate": "52000.00",
            "overtime_rate": "",
            "reason": "Annual performance appraisal revision.",
        })
        self.assertRedirects(response, reverse("employees:employee_detail", args=[self.employee.pk]))

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.base_salary_rate, Decimal("52000.00"))

        history = SalaryRateHistory.objects.filter(employee=self.employee).order_by("-effective_date")
        self.assertTrue(history.exists())
        latest = history.first()
        self.assertEqual(latest.base_rate, Decimal("52000.00"))
        self.assertEqual(latest.changed_by, self.accountant)
        self.assertEqual(latest.reason, "Annual performance appraisal revision.")

    def test_owner_cannot_modify_employee(self):
        self.client.force_login(self.owner)
        res = self.client.get(reverse("employees:employee_edit", args=[self.employee.pk]))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse("employees:salary_update", args=[self.employee.pk]))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse("employees:employee_delete", args=[self.employee.pk]))
        self.assertEqual(res.status_code, 403)

    def test_employee_delete_view_by_accountant(self):
        self.client.force_login(self.accountant)
        # GET confirm page
        get_res = self.client.get(reverse("employees:employee_delete", args=[self.employee.pk]))
        self.assertEqual(get_res.status_code, 200)

        # POST delete
        post_res = self.client.post(reverse("employees:employee_delete", args=[self.employee.pk]))
        self.assertRedirects(post_res, reverse("employees:employee_list"))
        self.assertFalse(Employee.objects.filter(pk=self.employee.pk).exists())

    def test_department_delete_view(self):
        self.client.force_login(self.accountant)
        empty_dept = Department.objects.create(name="Quality Control", code="QC")

        # Deleting empty department succeeds
        del_res = self.client.post(reverse("employees:department_delete", args=[empty_dept.pk]))
        self.assertRedirects(del_res, reverse("employees:department_list"))
        self.assertFalse(Department.objects.filter(pk=empty_dept.pk).exists())

        # Deleting department with assigned employee is blocked
        blocked_res = self.client.post(reverse("employees:department_delete", args=[self.dept.pk]))
        self.assertRedirects(blocked_res, reverse("employees:department_list"))
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())

    def test_bank_details_restricted_from_owner(self):
        """Owner viewing employee profile must NOT see confidential bank details."""
        self.employee.bank_name = "State Bank of India"
        self.employee.bank_account_number = "123456789012"
        self.employee.bank_ifsc_code = "SBIN0001234"
        self.employee.save()

        # As Accountant: bank details shown
        self.client.force_login(self.accountant)
        acct_res = self.client.get(reverse("employees:employee_detail", args=[self.employee.pk]))
        self.assertEqual(acct_res.status_code, 200)
        self.assertTrue(acct_res.context["show_bank_details"])
        self.assertContains(acct_res, "123456789012")

        # As Owner: bank details restricted
        self.client.force_login(self.owner)
        owner_res = self.client.get(reverse("employees:employee_detail", args=[self.employee.pk]))
        self.assertEqual(owner_res.status_code, 200)
        self.assertFalse(owner_res.context["show_bank_details"])
        self.assertNotContains(owner_res, "123456789012")
        self.assertContains(owner_res, "Disbursement and bank details are confidential")



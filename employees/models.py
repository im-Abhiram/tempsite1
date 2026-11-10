"""
Thamarayyath Employee Portal — Employee Profile Models.

Covers: Department, Designation, Shift, Employee, SalaryRateHistory, EmployeeDocument.
"""

import os
import uuid
import logging
import mimetypes
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger("portal")


# ─── Lookup Models ──────────────────────────────────────────────────────────────

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Designation(models.Model):
    name = models.CharField(max_length=150)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="designations")

    class Meta:
        unique_together = [("name", "department")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.department})"


class Shift(models.Model):
    """
    Represents a named working shift.
    Supports overnight shifts (e.g., 22:00 – 06:00 next day).
    """
    name = models.CharField(max_length=100, unique=True)
    start_time = models.TimeField(help_text="Shift start time (24h)")
    end_time = models.TimeField(help_text="Shift end time (24h)")
    unpaid_break_minutes = models.PositiveIntegerField(
        default=0, help_text="Unpaid break deducted from net hours"
    )
    is_night_shift = models.BooleanField(
        default=False,
        help_text="Check if shift spans midnight (end_time < start_time).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.start_time:%H:%M}–{self.end_time:%H:%M})"

    def clean(self):
        # Auto-detect night shift if times suggest crossing midnight
        if self.start_time and self.end_time:
            if self.end_time < self.start_time and not self.is_night_shift:
                raise ValidationError(
                    "End time is before start time. If this is an overnight shift, "
                    "enable the 'Is Night Shift' option."
                )


# ─── Employee Profile ───────────────────────────────────────────────────────────

class EmploymentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    RESIGNED = "RESIGNED", "Resigned"
    TERMINATED = "TERMINATED", "Terminated"


class EmploymentType(models.TextChoices):
    FULL_TIME = "FULL_TIME", "Full-Time"
    PART_TIME = "PART_TIME", "Part-Time"
    CONTRACT = "CONTRACT", "Contract"
    TEMPORARY = "TEMPORARY", "Temporary"
    DAILY_WAGE = "DAILY_WAGE", "Daily Wage"


class SalaryMethod(models.TextChoices):
    HOURLY = "HOURLY", "Hourly Rate"
    DAILY_WAGE = "DAILY_WAGE", "Daily Wage Rate"
    MONTHLY = "MONTHLY", "Monthly Salary"


def _employee_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"employee_photos/{instance.employee_id}{ext}"


def _generate_employee_id():
    """Auto-generate a sequential EMP-XXXX identifier."""
    last = Employee.objects.order_by("-id").first()
    if last and last.id:
        return f"EMP-{(last.id + 1):04d}"
    return "EMP-0001"


class WeekDay(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class Employee(models.Model):
    """Core employee profile. All PII fields are stored in the database only."""

    # Identification
    employee_id = models.CharField(max_length=20, unique=True, db_index=True)

    # Personal
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    photo = models.ImageField(
        upload_to=_employee_photo_path, null=True, blank=True,
        help_text="Optional employee photograph (stored in media directory).",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20,
        choices=[("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other"), ("PREFER_NOT", "Prefer Not to Say")],
        blank=True,
    )
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    residential_address = models.TextField()

    # Emergency Contact (Optional)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)

    # Employment
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT, related_name="employees")
    date_of_joining = models.DateField()
    employment_status = models.CharField(
        max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE, db_index=True
    )
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices)

    # Schedule
    assigned_shift = models.ForeignKey(
        Shift, null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    weekly_off_days = models.JSONField(
        default=list,
        help_text="List of integers 0-6 (Mon-Sun) representing weekly off days.",
    )
    standard_working_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("8.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )

    # Compensation (current effective rate is determined by SalaryRateHistory)
    salary_calculation_method = models.CharField(
        max_length=20, choices=SalaryMethod.choices, default=SalaryMethod.MONTHLY
    )
    base_salary_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Hourly rate / Daily rate / Monthly salary, per salary_calculation_method.",
    )
    overtime_eligible = models.BooleanField(default=True)
    custom_overtime_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="If set, overrides company default overtime multiplier.",
    )

    notes = models.TextField(blank=True)

    # Bank Details (optional and restricted — confidential access)
    bank_name = models.CharField(
        max_length=150, blank=True,
        help_text="Bank name (Confidential - restricted access)",
    )
    bank_account_number = models.CharField(
        max_length=50, blank=True,
        help_text="Bank account number (Confidential - restricted access)",
    )
    bank_ifsc_code = models.CharField(
        max_length=20, blank=True,
        help_text="IFSC / Branch code (Confidential - restricted access)",
    )
    bank_branch_name = models.CharField(
        max_length=150, blank=True,
        help_text="Branch name (Confidential - restricted access)",
    )

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="employees_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]
        indexes = [
            models.Index(fields=["employment_status"]),
            models.Index(fields=["department"]),
        ]

    def __str__(self):
        return f"{self.employee_id} — {self.full_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_active(self):
        return self.employment_status == EmploymentStatus.ACTIVE

    def save(self, *args, **kwargs):
        if not self.employee_id:
            self.employee_id = _generate_employee_id()
        super().save(*args, **kwargs)


# ─── Salary Rate History ─────────────────────────────────────────────────────────

class SalaryRateHistory(models.Model):
    """
    Records every salary rate change with effective dates.
    The current rate is the entry with end_date=None.
    Prevents silent modification of historical payroll by preserving historical rates.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="salary_history")
    effective_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    salary_calculation_method = models.CharField(max_length=20, choices=SalaryMethod.choices)
    base_rate = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    overtime_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Absolute hourly OT rate. If null, uses company multiplier * base hourly rate.",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="salary_changes_made",
    )
    reason = models.TextField(help_text="Mandatory reason for salary rate change.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date"]
        indexes = [models.Index(fields=["employee", "effective_date"])]

    def __str__(self):
        return (
            f"{self.employee.employee_id} {self.salary_calculation_method} "
            f"₹{self.base_rate} from {self.effective_date}"
        )


# ─── Employee Document Vault ─────────────────────────────────────────────────────

class DocumentType(models.TextChoices):
    IDENTITY = "IDENTITY", "Identity Document"
    EMPLOYMENT = "EMPLOYMENT", "Employment Document"
    OFFER_LETTER = "OFFER_LETTER", "Offer Letter"
    CONTRACT = "CONTRACT", "Contract"
    CERTIFICATE = "CERTIFICATE", "Certificate"
    OTHER = "OTHER", "Other"


def _private_vault_path(instance, filename):
    """
    Generate a UUID-based storage path completely independent of the original filename.
    Stored inside employee_documents/ directory.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"employee_documents/{uuid.uuid4().hex}{ext}"


class EmployeeDocument(models.Model):
    """
    Stores employee documents in the private vault (outside MEDIA_ROOT).
    Access is controlled by the view layer — never served from a predictable URL.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=_private_vault_path)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    detected_content_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.employee.employee_id} — {self.title}"

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 ** 2:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / 1024**2:.1f} MB"


# Model alias per specification
SalaryHistory = SalaryRateHistory


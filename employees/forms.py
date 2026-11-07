"""
Thamarayyath Employee Portal — Employee Forms.
All forms enforce server-side validation and respect role restrictions.
"""

import os
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import (
    Employee, Department, Designation, Shift, SalaryRateHistory,
    EmployeeDocument, DocumentType, SalaryMethod,
)


# ─── Department / Designation / Shift Forms ─────────────────────────────────────

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control text-uppercase"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ["name", "department"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "department": forms.Select(attrs={"class": "form-select"}),
        }


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ["name", "start_time", "end_time", "unpaid_break_minutes", "is_night_shift", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "start_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "unpaid_break_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_night_shift": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


# ─── Employee Profile Form ───────────────────────────────────────────────────────

WEEKLY_DAY_CHOICES = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"),
    (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class EmployeeForm(forms.ModelForm):
    weekly_off_days = forms.MultipleChoiceField(
        choices=WEEKLY_DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        required=False,
        help_text="Select all weekly off days for this employee.",
    )

    class Meta:
        model = Employee
        exclude = ["employee_id", "created_by", "created_at", "updated_at"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "photo": forms.FileInput(attrs={"class": "form-control"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "type": "tel"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "residential_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "emergency_contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "emergency_contact_phone": forms.TextInput(attrs={"class": "form-control", "type": "tel"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "designation": forms.Select(attrs={"class": "form-select"}),
            "date_of_joining": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "employment_status": forms.Select(attrs={"class": "form-select"}),
            "employment_type": forms.Select(attrs={"class": "form-select"}),
            "assigned_shift": forms.Select(attrs={"class": "form-select"}),
            "standard_working_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "salary_calculation_method": forms.Select(attrs={"class": "form-select"}),
            "base_salary_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "overtime_eligible": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "custom_overtime_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "bank_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. State Bank of India"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Bank Account Number"}),
            "bank_ifsc_code": forms.TextInput(attrs={"class": "form-control text-uppercase", "placeholder": "e.g. SBIN0001234"}),
            "bank_branch_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Branch Name"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.weekly_off_days:
            self.initial["weekly_off_days"] = [str(d) for d in self.instance.weekly_off_days]

    def clean_weekly_off_days(self):
        days = self.cleaned_data.get("weekly_off_days", [])
        return [int(d) for d in days]

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size"):
            max_size = 2 * 1024 * 1024  # 2 MB for photos
            if photo.size > max_size:
                raise ValidationError("Photo must be smaller than 2 MB.")
        return photo


# ─── Salary Rate Update Form ─────────────────────────────────────────────────────

class SalaryRateUpdateForm(forms.Form):
    """
    Used when updating an employee's salary. Creates a new SalaryRateHistory entry
    rather than modifying the employee record directly.
    """
    effective_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        help_text="Date from which this new rate takes effect.",
    )
    salary_calculation_method = forms.ChoiceField(
        choices=SalaryMethod.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    base_rate = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Hourly / Daily / Monthly base rate, per salary method.",
    )
    overtime_rate = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Absolute OT hourly rate. Leave blank to use company multiplier.",
    )
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        help_text="Mandatory reason for salary change (stored in audit history).",
    )


# ─── Document Upload Form ────────────────────────────────────────────────────────

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ["document_type", "title", "file", "notes"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "file": forms.FileInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data.get("file")
        if not uploaded_file:
            return uploaded_file

        # 1. File size check
        max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10) * 1024 * 1024
        if uploaded_file.size > max_bytes:
            raise ValidationError(
                f"File size {uploaded_file.size // 1024} KB exceeds the "
                f"{settings.MAX_UPLOAD_SIZE_MB} MB limit."
            )

        # 2. Extension check (cannot be trusted alone, but first pass)
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        allowed_exts = getattr(settings, "ALLOWED_DOC_EXTENSIONS", set())
        if ext not in allowed_exts:
            raise ValidationError(
                f"File type '{ext}' is not permitted. "
                f"Allowed: {', '.join(sorted(allowed_exts))}"
            )

        # 3. MIME sniffing from actual file content (not browser-supplied type)
        header = uploaded_file.read(2048)
        uploaded_file.seek(0)
        detected_mime = _detect_mime(header, uploaded_file.name)
        allowed_mimes = getattr(settings, "ALLOWED_DOC_MIME_TYPES", set())
        if detected_mime not in allowed_mimes:
            raise ValidationError(
                f"The file content appears to be '{detected_mime}', which is not permitted."
            )

        # Store detected MIME for later reference
        uploaded_file._detected_mime = detected_mime
        return uploaded_file


def _detect_mime(header_bytes: bytes, filename: str) -> str:
    """
    Attempt MIME detection from file content bytes.
    Falls back to filename-based guessing if python-magic is not available.
    """
    try:
        import magic as libmagic
        mime = libmagic.from_buffer(header_bytes, mime=True)
        return mime
    except (ImportError, Exception):
        # Fallback: use mimetypes (less reliable, extension-based)
        import mimetypes
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/octet-stream"

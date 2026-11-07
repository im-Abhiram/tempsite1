"""
Thamarayyath Employee Portal — Attendance Forms.
"""

import datetime
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from employees.models import Employee, Department
from .models import AttendanceRecord, AttendanceStatus, AttendanceEntryMethod, Holiday


class AttendanceMarkForm(forms.ModelForm):
    """
    For manual attendance entry (Accountant).
    check_in and check_out are entered as date-time inputs.
    """
    work_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    check_in_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        label="Check-In Time",
    )
    check_out_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        label="Check-Out Time",
    )
    is_overnight = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Overnight Shift (check-out is next day)",
        help_text="Enable for shifts that cross midnight.",
    )
    overtime_hours = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.25",
            "placeholder": "e.g. 2.0 (leave blank for auto-calculation)"
        }),
        label="Overtime Hours (Optional Override)",
        help_text="Enter custom approved overtime hours, or leave blank to calculate from punch duration.",
    )

    class Meta:
        model = AttendanceRecord
        fields = [
            "work_date", "check_in_time", "check_out_time", "is_overnight",
            "break_duration_minutes", "overtime_hours", "status", "correction_reason",
        ]
        widgets = {
            "break_duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "correction_reason": forms.Textarea(attrs={
                "class": "form-control", "rows": 2,
                "placeholder": "Add any remarks, overtime authorization notes, or special circumstances..."
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        work_date = cleaned_data.get("work_date")
        check_in_time = cleaned_data.get("check_in_time")
        check_out_time = cleaned_data.get("check_out_time")
        is_overnight = cleaned_data.get("is_overnight", False)
        status = cleaned_data.get("status")

        # Validate check-in/out are provided for PRESENT/HALF_DAY
        if status in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY):
            if not check_in_time:
                raise ValidationError({"check_in_time": "Check-in time is required for present/half-day attendance."})

        if check_in_time and check_out_time and work_date:
            from django.utils.timezone import make_aware, get_current_timezone
            tz = get_current_timezone()
            check_in_dt = make_aware(
                datetime.datetime.combine(work_date, check_in_time), tz
            )
            check_out_date = work_date + datetime.timedelta(days=1) if is_overnight else work_date
            check_out_dt = make_aware(
                datetime.datetime.combine(check_out_date, check_out_time), tz
            )

            if check_out_dt <= check_in_dt:
                raise ValidationError(
                    "Check-out must be after check-in. "
                    "For overnight shifts, enable the 'Overnight Shift' option."
                )

            cleaned_data["_check_in_dt"] = check_in_dt
            cleaned_data["_check_out_dt"] = check_out_dt

        return cleaned_data


class AttendanceCorrectionForm(forms.ModelForm):
    """Used to correct existing attendance records (requires mandatory reason)."""
    check_in_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    check_out_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
    )
    is_overnight = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    overtime_hours = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.25",
            "placeholder": "e.g. 2.0 (leave blank to calculate from duration)"
        }),
        label="Overtime Hours (Optional Override)",
        help_text="Directly adjust overtime hours or leave blank to recalculate.",
    )

    class Meta:
        model = AttendanceRecord
        fields = [
            "check_in_time", "check_out_time", "is_overnight",
            "break_duration_minutes", "overtime_hours", "status", "correction_reason",
        ]
        widgets = {
            "break_duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "correction_reason": forms.Textarea(attrs={
                "class": "form-control", "rows": 3,
                "placeholder": "Mandatory: reason for correction and any overtime notes"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["overtime_hours"].initial = self.instance.overtime_hours

    def clean_correction_reason(self):
        reason = self.cleaned_data.get("correction_reason", "").strip()
        if not reason:
            raise ValidationError("A correction reason is mandatory.")
        if len(reason) < 10:
            raise ValidationError("Correction reason must be at least 10 characters.")
        return reason


class AttendanceDateRangeFilterForm(forms.Form):
    """Filter form for attendance list views."""
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(employment_status="ACTIVE"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    status = forms.ChoiceField(
        choices=[("", "All Statuses")] + AttendanceStatus.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ["name", "date", "is_paid"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_paid": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class LeaveRecordForm(forms.ModelForm):
    class Meta:
        from .models import LeaveRecord
        model = LeaveRecord
        fields = ["employee", "leave_type", "start_date", "end_date", "reason", "status"]
        widgets = {
            "employee": forms.Select(attrs={"class": "form-select"}),
            "leave_type": forms.Select(attrs={"class": "form-select"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date cannot be earlier than start date.")
        return cleaned_data


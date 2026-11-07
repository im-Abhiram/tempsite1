"""Thamarayyath Employee Portal — Payroll Forms."""

import datetime
from django import forms
from accounts.models import PayrollCycle
from .models import PayrollPeriod, PayrollStatus


class GeneratePayrollForm(forms.Form):
    cycle_type = forms.ChoiceField(
        choices=PayrollCycle.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Payroll Cycle",
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Period Start Date",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label="Period End Date",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        label="Notes (optional)",
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        cycle = cleaned_data.get("cycle_type")

        if start and end:
            if end <= start:
                raise forms.ValidationError("End date must be after start date.")
            duration = (end - start).days + 1

            expected = {"WEEKLY": 7, "BIWEEKLY": 14, "THREE_WEEKLY": 21}
            if cycle in expected and duration != expected[cycle]:
                raise forms.ValidationError(
                    f"{dict(PayrollCycle.choices)[cycle]} payroll must cover exactly "
                    f"{expected[cycle]} days (you specified {duration} days)."
                )
        return cleaned_data


class PayrollReviewForm(forms.Form):
    """Confirmation form for reviewing a payroll period."""
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        label="Reviewer Notes",
    )


class PayrollFinalizeForm(forms.Form):
    """Confirmation form with required acknowledgement checkbox."""
    confirm = forms.BooleanField(
        required=True,
        label="I confirm that this payroll period is correct and ready for finalization.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

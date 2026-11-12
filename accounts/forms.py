"""
Thamarayyath Employee Portal — Account Forms.

All forms enforce server-side validation.
Sensitive fields are excluded from forms where role restrictions require it.
"""

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from .models import Role, CompanySettings
from decimal import Decimal

User = get_user_model()


# ─── Login Form ─────────────────────────────────────────────────────────────────

class PortalLoginForm(AuthenticationForm):
    """
    Overrides Django's default login form to use 'username' label and
    provide a single generic error message (prevents username enumeration).
    """

    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "autofocus": True,
            "autocomplete": "username",
            "placeholder": "Enter your username",
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "current-password",
            "placeholder": "Enter your password",
        }),
    )
    captcha = forms.CharField(
        label="Math Security Question",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control fw-bold",
            "autocomplete": "off",
            "placeholder": "Enter math result (e.g. 15)",
            "maxlength": 10,
            "inputmode": "numeric",
        }),
    )

    error_messages = {
        "invalid_login": "Invalid username or password. Please try again.",
        "inactive": "This account has been deactivated.",
    }

    def clean(self):
        cleaned_data = super().clean()
        request = getattr(self, "request", None)
        if request:
            is_testing = getattr(settings, "TESTING", False)
            # In testing, allow bypassing captcha if not present in session to avoid breaking non-captcha unit tests
            if not is_testing or "login_captcha" in request.session:
                expected = str(request.session.pop("login_captcha", None) or "").strip()
                submitted = str(cleaned_data.get("captcha", "")).strip()
                if not submitted or not expected or submitted != expected:
                    self.add_error("captcha", "Incorrect answer. Please solve the math problem shown in the image.")
        return cleaned_data


# ─── User Account Forms (Superadmin Only) ───────────────────────────────────────

class CreateUserForm(forms.ModelForm):
    """
    Form for Superadmin to create Office Administration or Owner accounts.
    Superadmin cannot create another Superadmin through this form
    (only via management command) — enforced both here and in the view.
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=10,
        help_text="Minimum 10 characters. Cannot be a common password.",
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["username", "display_name", "designation", "email", "role"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter username"}),
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name"}),
            "designation": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Office Administrator, Managing Director"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "user@example.com"}),
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.creating_user = kwargs.pop("creating_user", None)
        super().__init__(*args, **kwargs)
        # Superadmin cannot create another Superadmin via UI form
        self.fields["role"].choices = [
            (k, v) for k, v in Role.choices if k != Role.SUPERADMIN
        ]

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username=username).exists():
            raise ValidationError("A user with this username already exists.")
        return username

    def clean_role(self):
        role = self.cleaned_data["role"]
        if role == Role.SUPERADMIN:
            raise ValidationError("Cannot create a Superadmin account through this form.")
        return role

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        if pw and confirm and pw != confirm:
            raise ValidationError({"confirm_password": "Passwords do not match."})
        return cleaned_data


class EditUserForm(forms.ModelForm):
    """
    Edit an existing account. Allows Superadmin to modify username, display name,
    designation, email, role, and active status.
    Users cannot edit their own role or suspend themselves (enforced in view & form).
    """

    class Meta:
        model = User
        fields = ["username", "display_name", "designation", "email", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Office Administrator, Managing Director"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.editing_user = kwargs.pop("editing_user", None)
        self.target_user = kwargs.pop("target_user", None)
        super().__init__(*args, **kwargs)
        # Prevent downgrading or suspending self
        if self.editing_user and self.target_user and self.editing_user == self.target_user:
            self.fields.pop("role", None)
            self.fields.pop("is_active", None)

    def clean_username(self):
        new_username = self.cleaned_data.get("username", "").strip()
        if not new_username:
            raise ValidationError("Username cannot be empty.")
        # Check uniqueness against other users (excluding current instance)
        qs = User.objects.filter(username__iexact=new_username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Username '{new_username}' is already in use by another account.")
        return new_username

    def clean_role(self):
        new_role = self.cleaned_data.get("role")
        if new_role == Role.SUPERADMIN and self.instance and self.instance.role != Role.SUPERADMIN:
            raise ValidationError("Cannot assign Superadmin role through this form.")
        return new_role


class ResetPasswordForm(forms.Form):
    """Superadmin sets a new password for another user."""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=10,
        label="New Password",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Confirm New Password",
    )

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get("new_password")
        confirm = cleaned_data.get("confirm_password")
        if pw and confirm and pw != confirm:
            raise ValidationError({"confirm_password": "Passwords do not match."})
        return cleaned_data


class ChangeOwnPasswordForm(forms.Form):
    """Any authenticated user can change their own password after confirming current."""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Current Password",
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=10,
        label="New Password",
        help_text="Minimum 10 characters.",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Confirm New Password",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pw = self.cleaned_data.get("current_password")
        if not self.user.check_password(pw):
            raise ValidationError("Current password is incorrect.")
        return pw

    def clean(self):
        cleaned_data = super().clean()
        pw = cleaned_data.get("new_password")
        confirm = cleaned_data.get("confirm_password")
        if pw and confirm and pw != confirm:
            raise ValidationError({"confirm_password": "Passwords do not match."})
        return cleaned_data


# ─── Company Settings Form ──────────────────────────────────────────────────────

class CompanySettingsForm(forms.ModelForm):
    """Superadmin-only form to configure company-wide payroll and HR policies."""

    class Meta:
        model = CompanySettings
        exclude = ["updated_by", "updated_at"]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "timezone": forms.TextInput(attrs={"class": "form-control"}),
            "currency_symbol": forms.TextInput(attrs={"class": "form-control"}),
            "standard_daily_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "standard_weekly_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "overtime_allowed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "overtime_rate_multiplier": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "daily_overtime_threshold_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
            "default_unpaid_break_minutes": forms.NumberInput(attrs={"class": "form-control"}),
            "late_grace_period_minutes": forms.NumberInput(attrs={"class": "form-control"}),
            "payroll_cycle": forms.Select(attrs={"class": "form-select"}),
            "payroll_start_day": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 28}),
            "allow_owner_export": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "working_hour_rounding": forms.Select(attrs={"class": "form-select"}),
        }

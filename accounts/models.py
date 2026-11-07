"""
Thamarayyath Employee Portal — Custom User Model & Account Management Models.

Roles
-----
SUPERADMIN  — Full system control, account management, configuration.
ACCOUNTANT  — Employee records, attendance, payroll operations.
OWNER       — Read-only access to dashboards and reports.
"""

import logging
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.validators import MinValueValidator

logger = logging.getLogger("portal")


class Role(models.TextChoices):
    SUPERADMIN = "SUPERADMIN", "Superadmin"
    ACCOUNTANT = "ACCOUNTANT", "Accountant"
    OWNER = "OWNER", "Owner"


# ─── Custom User Manager ────────────────────────────────────────────────────────

class CustomUserManager(BaseUserManager):
    def create_user(self, username, password, role, created_by=None, **extra_fields):
        if not username:
            raise ValueError("Username is required.")
        if not password:
            raise ValueError("Password is required.")
        if role not in Role.values:
            raise ValueError(f"Role must be one of: {Role.values}")
        user = self.model(username=username.strip().lower(), role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        logger.info(
            "User created: username=%s role=%s by=%s",
            user.username,
            user.role,
            created_by,
        )
        return user

    def create_superadmin(self, username, password, **extra_fields):
        """Convenience method for the initial Superadmin created via management command."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", False)  # We use role checks, not Django perms
        extra_fields.pop("role", None)
        return self.create_user(username, password, Role.SUPERADMIN, **extra_fields)

    def create_superuser(self, username, password, **extra_fields):
        """Django compatibility alias."""
        return self.create_superadmin(username, password, **extra_fields)


# ─── Custom User Model ──────────────────────────────────────────────────────────

class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Central user model for the portal.
    Roles are enforced server-side on every request.
    Users cannot self-promote or change their own role.
    """

    username = models.CharField(max_length=100, unique=True, db_index=True)
    display_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Required for Django internals
    is_superuser = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    # Login throttling state
    failed_login_attempts = models.PositiveIntegerField(default=0)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"
        ordering = ["username"]

    def __str__(self):
        return f"{self.display_name or self.username} ({self.get_role_display()})"

    # ─── Role Helpers ─────────────────────────────────────────────────────────

    @property
    def is_superadmin(self):
        return self.role == Role.SUPERADMIN

    @property
    def is_accountant(self):
        return self.role == Role.ACCOUNTANT

    @property
    def is_owner(self):
        return self.role == Role.OWNER

    # ─── Account Lock State ───────────────────────────────────────────────────

    def is_locked(self):
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    def record_failed_login(self, max_attempts, lockout_minutes):
        from django.conf import settings
        self.failed_login_attempts += 1
        self.last_failed_login = timezone.now()
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lockout_minutes)
            logger.warning(
                "Account locked: username=%s until=%s",
                self.username,
                self.locked_until,
            )
        self.save(update_fields=["failed_login_attempts", "last_failed_login", "locked_until"])

    def record_successful_login(self, ip_address=None):
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.locked_until = None
        self.last_login = timezone.now()
        if ip_address:
            self.last_login_ip = ip_address
        self.save(update_fields=[
            "failed_login_attempts", "last_failed_login",
            "locked_until", "last_login", "last_login_ip",
        ])


# ─── Company Settings ───────────────────────────────────────────────────────────

class PayrollCycle(models.TextChoices):
    WEEKLY = "WEEKLY", "Weekly (7 days)"
    BIWEEKLY = "BIWEEKLY", "Biweekly (14 days)"
    THREE_WEEKLY = "THREE_WEEKLY", "Three-Weekly (21 days)"
    MONTHLY = "MONTHLY", "Monthly"


class CompanySettings(models.Model):
    """
    Singleton configuration record for company-wide policies.
    Only the Superadmin can modify this record.
    """

    company_name = models.CharField(max_length=200, default="Thamarayyath")
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    currency_symbol = models.CharField(max_length=5, default="₹")

    # Working hour defaults
    standard_daily_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("8.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    standard_weekly_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("48.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )

    # Overtime
    overtime_allowed = models.BooleanField(default=True)
    overtime_rate_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.50"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    daily_overtime_threshold_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("8.00"),
    )

    # Break
    default_unpaid_break_minutes = models.PositiveIntegerField(default=0)

    # Late arrival grace
    late_grace_period_minutes = models.PositiveIntegerField(default=15)

    # Payroll cycle
    payroll_cycle = models.CharField(
        max_length=20, choices=PayrollCycle.choices, default=PayrollCycle.MONTHLY
    )
    payroll_start_day = models.PositiveSmallIntegerField(
        default=1, help_text="Day of month the payroll cycle starts (for Monthly/custom)"
    )

    # Permissions
    allow_owner_export = models.BooleanField(
        default=False, help_text="Allow Owner role to download report files"
    )

    # Rounding
    ROUND_CHOICES = [
        ("NONE", "No Rounding"),
        ("QUARTER", "Nearest 15 minutes"),
        ("HALF", "Nearest 30 minutes"),
        ("HOUR", "Nearest hour"),
    ]
    working_hour_rounding = models.CharField(
        max_length=10, choices=ROUND_CHOICES, default="NONE"
    )

    # Metadata
    updated_by = models.ForeignKey(
        CustomUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="company_settings_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Settings"
        verbose_name_plural = "Company Settings"

    def __str__(self):
        return f"{self.company_name} Settings"

    @classmethod
    def get(cls):
        """Get (or create with defaults) the singleton company settings record."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# Model alias per specification
ApplicationSetting = CompanySettings


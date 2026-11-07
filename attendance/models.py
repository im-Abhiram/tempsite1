"""
Thamarayyath Employee Portal — Attendance Models.

Supports overnight shifts, correct duration arithmetic,
immutable correction audit trail, and payroll locking.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

logger = logging.getLogger("portal")


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    HALF_DAY = "HALF_DAY", "Half-Day"
    PAID_LEAVE = "PAID_LEAVE", "Paid Leave"
    UNPAID_LEAVE = "UNPAID_LEAVE", "Unpaid Leave"
    WEEKLY_OFF = "WEEKLY_OFF", "Weekly Off"
    HOLIDAY = "HOLIDAY", "Holiday"
    INCOMPLETE = "INCOMPLETE", "Incomplete (Missing Check-Out)"


class AttendanceEntryMethod(models.TextChoices):
    SYSTEM = "SYSTEM", "System (Biometric / Auto)"
    MANUAL = "MANUAL", "Manual Entry"
    IMPORT = "IMPORT", "Bulk Import"
    CORRECTION = "CORRECTION", "Manual Correction"


class AttendanceRecord(models.Model):
    """
    One record per employee per work date (for standard shifts).
    Split shifts: enforce uniqueness through application logic.

    Working hour calculation:
        net_working_hours = (check_out - check_in) - break_duration_minutes
    All datetime fields are stored as UTC; display is converted to company timezone.
    """

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        db_index=True,
    )
    work_date = models.DateField(db_index=True)

    # Timestamps — stored as timezone-aware UTC datetimes
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    # Breaks
    break_duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Unpaid break duration deducted from net working hours.",
    )

    # Calculated fields (stored for performance; recalculate if attendance changes)
    net_working_hours = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000"),
        help_text="Net hours after break deduction. Calculated automatically.",
    )
    overtime_hours = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000"),
        help_text="Overtime hours above the standard daily threshold.",
    )
    regular_hours = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.0000"),
        help_text="Hours counted as regular (non-overtime).",
    )

    # Status and flags
    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.INCOMPLETE,
        db_index=True,
    )
    entry_method = models.CharField(
        max_length=20, choices=AttendanceEntryMethod.choices, default=AttendanceEntryMethod.MANUAL
    )
    is_late = models.BooleanField(default=False)
    late_by_minutes = models.PositiveIntegerField(default=0)
    is_early_departure = models.BooleanField(default=False)
    early_by_minutes = models.PositiveIntegerField(default=0)

    # Payroll lock: set True when this record is included in a finalized payroll
    is_locked_by_payroll = models.BooleanField(
        default=False,
        help_text="Set to True when payroll referencing this record is finalized.",
    )
    payroll_period_id = models.IntegerField(
        null=True, blank=True,
        help_text="FK reference (loose) to the payroll period that locked this record.",
    )

    correction_reason = models.TextField(
        blank=True,
        help_text="Required if this record was manually corrected.",
    )

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_created",
    )
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_modified",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("employee", "work_date")]
        ordering = ["-work_date", "employee"]
        indexes = [
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["work_date", "status"]),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} | {self.work_date} | {self.get_status_display()}"

    def calculate_hours(self, daily_threshold_hours: Decimal = Decimal("8.00")):
        """
        Recalculate net_working_hours, regular_hours, and overtime_hours.

        Uses accurate datetime subtraction (no premature rounding).
        Supports overnight shifts (check_out on the next day).
        """
        if not self.check_in or not self.check_out:
            self.net_working_hours = Decimal("0.0000")
            self.regular_hours = Decimal("0.0000")
            self.overtime_hours = Decimal("0.0000")
            return

        if self.check_out <= self.check_in:
            logger.warning(
                "Invalid attendance: check_out <= check_in for emp=%s date=%s",
                self.employee_id, self.work_date,
            )
            self.net_working_hours = Decimal("0.0000")
            self.regular_hours = Decimal("0.0000")
            self.overtime_hours = Decimal("0.0000")
            return

        # Duration in seconds → convert to decimal hours
        duration_seconds = (self.check_out - self.check_in).total_seconds()
        break_seconds = self.break_duration_minutes * 60
        net_seconds = max(0, duration_seconds - break_seconds)

        # Use high-precision Decimal arithmetic
        net_hours = Decimal(str(net_seconds)) / Decimal("3600")
        net_hours = net_hours.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        self.net_working_hours = net_hours

        # Regular vs overtime split
        threshold = Decimal(str(daily_threshold_hours))
        if net_hours > threshold and self.employee.overtime_eligible:
            self.regular_hours = threshold
            self.overtime_hours = (net_hours - threshold).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        else:
            self.regular_hours = net_hours
            self.overtime_hours = Decimal("0.0000")

    def calculate_late_flag(self, grace_period_minutes: int = 0):
        """
        Determine if check-in was late, comparing against the assigned shift's start time.
        """
        if not self.check_in or not self.employee.assigned_shift:
            return

        shift = self.employee.assigned_shift
        # Build the expected check-in datetime for the work_date
        from django.utils.timezone import make_aware
        import datetime
        expected_dt = make_aware(
            datetime.datetime.combine(self.work_date, shift.start_time),
            timezone.get_current_timezone(),
        )
        grace = datetime.timedelta(minutes=grace_period_minutes)
        check_in_local = timezone.localtime(self.check_in)

        if check_in_local > expected_dt + grace:
            late_delta = check_in_local - expected_dt
            self.is_late = True
            self.late_by_minutes = int(late_delta.total_seconds() // 60)
        else:
            self.is_late = False
            self.late_by_minutes = 0


class AttendanceCorrectionLog(models.Model):
    """
    Append-only log of every change made to an AttendanceRecord after creation.
    Corrections to payroll-locked records require an approved reopening (enforced in view).
    """

    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.CASCADE, related_name="correction_logs"
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    old_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    reason = models.TextField()
    is_post_payroll_correction = models.BooleanField(
        default=False,
        help_text="True if correction was made after payroll was finalized.",
    )

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return (
            f"Correction to {self.attendance_record} by "
            f"{self.modified_by} at {self.timestamp:%Y-%m-%d %H:%M}"
        )


class Holiday(models.Model):
    """Company-configured public and company holidays."""
    name = models.CharField(max_length=200)
    date = models.DateField(unique=True, db_index=True)
    is_paid = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.name} ({self.date})"


# ─── Leave Tracking ─────────────────────────────────────────────────────────────

class LeaveType(models.TextChoices):
    PAID_LEAVE = "PAID_LEAVE", "Paid Leave"
    UNPAID_LEAVE = "UNPAID_LEAVE", "Unpaid Leave"
    SICK_LEAVE = "SICK_LEAVE", "Sick Leave"
    CASUAL_LEAVE = "CASUAL_LEAVE", "Casual Leave"


class LeaveStatus(models.TextChoices):
    APPROVED = "APPROVED", "Approved"
    PENDING = "PENDING", "Pending"
    REJECTED = "REJECTED", "Rejected"


class LeaveRecord(models.Model):
    """
    Formal Leave records for employees.
    Used for attendance cross-referencing and leave summaries.
    """
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="leave_records"
    )
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.PAID_LEAVE)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=LeaveStatus.choices, default=LeaveStatus.APPROVED)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="leaves_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["employee", "start_date"]),
            models.Index(fields=["status", "start_date"]),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} — {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"

    @property
    def duration_days(self):
        if self.end_date and self.start_date:
            return (self.end_date - self.start_date).days + 1
        return 1


# Model aliases per specification
Attendance = AttendanceRecord
AttendanceCorrection = AttendanceCorrectionLog


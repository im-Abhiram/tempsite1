"""
Thamarayyath Employee Portal — Payroll Models.

Supports 4 pay cycles, 3 salary methods, immutable payroll snapshots,
and the Draft → Reviewed → Finalized → Reversed workflow.
Uses Decimal throughout for monetary precision.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from accounts.models import PayrollCycle

logger = logging.getLogger("portal")


class PayrollStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    REVIEWED = "REVIEWED", "Reviewed"
    FINALIZED = "FINALIZED", "Finalized"
    REVERSED = "REVERSED", "Reversed"
    ADJUSTED = "ADJUSTED", "Adjusted (Replaced by Correction)"


# ─── Payroll Period ─────────────────────────────────────────────────────────────

class PayrollPeriod(models.Model):
    """
    Represents a payroll cycle (weekly / biweekly / 3-weekly / monthly).
    One PayrollPeriod → many PayrollStatements (one per employee).
    """

    cycle_type = models.CharField(max_length=20, choices=PayrollCycle.choices)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    department = models.ForeignKey(
        "employees.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payroll_periods",
        help_text="Specific department or blank for all departments in organization.",
    )
    status = models.CharField(
        max_length=20, choices=PayrollStatus.choices, default=PayrollStatus.DRAFT, db_index=True
    )

    # Workflow tracking
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="payroll_generated"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payroll_reviewed"
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payroll_finalized"
    )
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payroll_reversed"
    )

    generated_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("cycle_type", "start_date", "end_date", "department")]
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["status", "start_date"]),
        ]

    def __str__(self):
        dept_str = f" ({self.department.name})" if self.department else " (All Departments)"
        return f"{self.get_cycle_type_display()} | {self.start_date} – {self.end_date}{dept_str} [{self.status}]"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def total_net_pay(self):
        val = self.statements.aggregate(total=models.Sum("net_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_gross_pay(self):
        val = self.statements.aggregate(total=models.Sum("gross_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_overtime_pay(self):
        val = self.statements.aggregate(total=models.Sum("overtime_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_base_pay(self):
        val = self.statements.aggregate(total=models.Sum("base_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_allowances(self):
        val = self.statements.aggregate(total=models.Sum("total_allowances"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_bonuses(self):
        val = self.statements.aggregate(total=models.Sum("total_bonuses"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_deductions(self):
        val = self.statements.aggregate(total=models.Sum("total_deductions"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_paid_count(self):
        return self.statements.filter(is_paid=True).count()

    @property
    def total_unpaid_count(self):
        return self.statements.filter(is_paid=False).count()

    @property
    def total_paid_amount(self):
        val = self.statements.filter(is_paid=True).aggregate(total=models.Sum("net_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def total_unpaid_amount(self):
        val = self.statements.filter(is_paid=False).aggregate(total=models.Sum("net_pay"))["total"]
        return val if val is not None else Decimal("0.00")

    @property
    def created_at(self):
        return self.generated_at

    @property
    def created_by(self):
        return self.generated_by

    def validate_no_overlap(self):
        """Prevent overlapping payroll periods of the same cycle type for the same department or all departments."""
        qs = PayrollPeriod.objects.filter(
            cycle_type=self.cycle_type,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(status=PayrollStatus.REVERSED).exclude(pk=self.pk)

        if self.department:
            overlapping = qs.filter(models.Q(department=self.department) | models.Q(department__isnull=True))
        else:
            overlapping = qs

        if overlapping.exists():
            dup = overlapping.first()
            dept_name = dup.department.name if dup.department else "All Departments"
            raise ValueError(
                f"Payroll period {self.start_date}–{self.end_date} overlaps with "
                f"an existing {self.cycle_type} period ({dept_name})."
            )


# ─── Payroll Statement (Immutable Snapshot) ─────────────────────────────────────

class PayrollStatement(models.Model):
    """
    Immutable snapshot of a single employee's payroll for one PayrollPeriod.
    Once finalized, this record must not be modified.
    The calculation_breakdown JSON stores the full computation for auditability.
    """

    payroll_period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="statements"
    )
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.PROTECT, related_name="payroll_statements"
    )

    # Salary method snapshot (captured at generation time)
    salary_method = models.CharField(max_length=20)
    base_rate = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))
    overtime_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # Hours summary
    scheduled_hours = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    worked_hours = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    regular_hours = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    payable_days = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0000"))
    unpaid_leave_days = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0000"))
    paid_leave_days = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0000"))
    absent_days = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0000"))

    # Pay components (Decimal precision, stored as currency)
    base_pay = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    overtime_pay = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_allowances = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_bonuses = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    gross_pay = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # Status (mirrors PayrollPeriod but per-employee)
    status = models.CharField(
        max_length=20, choices=PayrollStatus.choices, default=PayrollStatus.DRAFT
    )

    # Full calculation audit trail
    calculation_breakdown = models.JSONField(
        default=dict,
        help_text="Complete calculation details: attendance dates, rates, formulas.",
    )

    # Workflow
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="statements_finalized"
    )

    # Wage Disbursement / Payment Tracking
    is_paid = models.BooleanField(
        default=False, db_index=True,
        help_text="True if wages have been disbursed to the employee."
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="statements_paid"
    )
    payment_method = models.CharField(
        max_length=50, default="BANK_TRANSFER",
        choices=[
            ("BANK_TRANSFER", "Bank Transfer"),
            ("CASH", "Cash"),
            ("CHEQUE", "Cheque"),
            ("UPI", "UPI"),
        ],
        blank=True,
    )
    payment_remarks = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("payroll_period", "employee")]
        ordering = ["employee__employee_id"]

    def __str__(self):
        return f"{self.employee.employee_id} | {self.payroll_period} | ₹{self.net_pay}"

    def mark_paid(self, by_user, method="BANK_TRANSFER", remarks=""):
        self.is_paid = True
        self.paid_at = timezone.now()
        self.paid_by = by_user
        self.payment_method = method or "BANK_TRANSFER"
        self.payment_remarks = remarks or ""
        self.save(update_fields=["is_paid", "paid_at", "paid_by", "payment_method", "payment_remarks", "updated_at"])

    def mark_unpaid(self):
        self.is_paid = False
        self.paid_at = None
        self.paid_by = None
        self.payment_remarks = ""
        self.save(update_fields=["is_paid", "paid_at", "paid_by", "payment_remarks", "updated_at"])

    def finalize(self, by_user):
        """Mark statement as finalized and lock it. Must be called inside a transaction."""
        if self.status == PayrollStatus.FINALIZED:
            raise ValueError("Statement is already finalized.")
        self.status = PayrollStatus.FINALIZED
        self.finalized_at = timezone.now()
        self.finalized_by = by_user
        self.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])

        # Lock all attendance records within this period
        from attendance.models import AttendanceRecord
        AttendanceRecord.objects.filter(
            employee=self.employee,
            work_date__gte=self.payroll_period.start_date,
            work_date__lte=self.payroll_period.end_date,
        ).update(is_locked_by_payroll=True, payroll_period_id=self.payroll_period.pk)


# ─── Payroll Allowances & Deductions ────────────────────────────────────────────

class PayrollLineItem(models.Model):
    """Individual allowances or deductions for a PayrollStatement."""

    class LineType(models.TextChoices):
        ALLOWANCE = "ALLOWANCE", "Allowance"
        BONUS = "BONUS", "Bonus"
        DEDUCTION = "DEDUCTION", "Deduction"

    statement = models.ForeignKey(
        PayrollStatement, on_delete=models.CASCADE, related_name="line_items"
    )
    line_type = models.CharField(max_length=10, choices=LineType.choices)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_statutory = models.BooleanField(
        default=False, help_text="True for legally mandated deductions/benefits."
    )
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["line_type", "name"]

    def __str__(self):
        return f"{self.get_line_type_display()}: {self.name} ₹{self.amount}"


# ─── Payroll Adjustment / Reversal ──────────────────────────────────────────────

class PayrollAdjustment(models.Model):
    """
    Records corrections to finalized payroll.
    The original statement is marked ADJUSTED; a replacement statement (if applicable) replaces it.
    This preserves the complete audit chain.
    """
    original_statement = models.ForeignKey(
        PayrollStatement, on_delete=models.PROTECT, related_name="adjustments_as_original"
    )
    replacement_statement = models.ForeignKey(
        PayrollStatement, null=True, blank=True,
        on_delete=models.PROTECT, related_name="adjustments_as_replacement"
    )
    reason = models.TextField()
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="payroll_adjustments_authorized"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="payroll_adjustments_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Adjustment to {self.original_statement} at {self.created_at:%Y-%m-%d}"


# Convenience Proxy Models & Aliases per specification
class Allowance(PayrollLineItem):
    class Meta:
        proxy = True
        verbose_name = "Allowance"
        verbose_name_plural = "Allowances"


class Deduction(PayrollLineItem):
    class Meta:
        proxy = True
        verbose_name = "Deduction"
        verbose_name_plural = "Deductions"


PayrollRecord = PayrollStatement


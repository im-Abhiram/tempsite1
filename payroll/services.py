"""
Thamarayyath Employee Portal — Payroll Calculation Engine.

Supports: Weekly (7d), Biweekly (14d), Three-Weekly (21d), Monthly payroll.
Salary methods: Hourly, Daily-Wage, Monthly-Salaried.

All monetary arithmetic uses Python Decimal to avoid floating-point errors.
Round final currency values to 2dp using ROUND_HALF_UP.
"""

import logging
import datetime
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import Optional

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from accounts.models import CompanySettings
from attendance.models import AttendanceRecord, AttendanceStatus
from employees.models import Employee, Department, SalaryRateHistory, SalaryMethod
from .models import PayrollPeriod, PayrollStatement, PayrollLineItem, PayrollStatus

logger = logging.getLogger("portal")

TWO_DP = Decimal("0.01")
FOUR_DP = Decimal("0.0001")


# ─── Period Date Helpers ────────────────────────────────────────────────────────

def get_period_dates(cycle_type: str, reference_date: datetime.date, settings_obj: CompanySettings):
    """
    Calculate payroll period start and end dates from a reference date and cycle.
    Returns (start_date, end_date).
    """
    if cycle_type == "WEEKLY":
        # Week starting Monday through Sunday
        start = reference_date - datetime.timedelta(days=reference_date.weekday())
        end = start + datetime.timedelta(days=6)
    elif cycle_type == "BIWEEKLY":
        start = reference_date - datetime.timedelta(days=reference_date.weekday())
        end = start + datetime.timedelta(days=13)
    elif cycle_type == "THREE_WEEKLY":
        start = reference_date - datetime.timedelta(days=reference_date.weekday())
        end = start + datetime.timedelta(days=20)
    elif cycle_type == "MONTHLY":
        start_day = settings_obj.payroll_start_day or 1
        if reference_date.day >= start_day:
            start = reference_date.replace(day=start_day)
        else:
            # Previous month start
            first_of_month = reference_date.replace(day=1)
            prev_month = first_of_month - datetime.timedelta(days=1)
            start = prev_month.replace(day=min(start_day, prev_month.day))
        # End date = day before next period starts
        if start_day == 1:
            # Calendar month: last day of month
            import calendar
            last_day = calendar.monthrange(start.year, start.month)[1]
            end = start.replace(day=last_day)
        else:
            # Next period start minus 1 day
            next_month = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=start_day)
            end = next_month - datetime.timedelta(days=1)
    else:
        raise ValueError(f"Unknown cycle_type: {cycle_type}")

    return start, end


# ─── Effective Salary Rate Lookup ───────────────────────────────────────────────

def get_effective_rate(employee: Employee, as_of_date: datetime.date):
    """
    Return the SalaryRateHistory entry effective on `as_of_date`.
    Falls back to the employee's current rate if no history record exists.
    """
    rate = (
        SalaryRateHistory.objects
        .filter(employee=employee, effective_date__lte=as_of_date)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=as_of_date))
        .order_by("-effective_date")
        .first()
    )
    if rate:
        return rate
    # Fallback: employee record
    class _FallbackRate:
        salary_calculation_method = employee.salary_calculation_method
        base_rate = employee.base_salary_rate
        overtime_rate = employee.custom_overtime_rate
    return _FallbackRate()


# ─── Core Calculation: Per Employee, Per Period ──────────────────────────────────

def calculate_employee_payroll(
    employee: Employee,
    period: PayrollPeriod,
    settings_obj: CompanySettings,
    requested_by,
) -> PayrollStatement:
    """
    Calculate payroll for one employee for the given period.
    Returns an unsaved PayrollStatement ready for persistence.

    Steps:
    1. Fetch attendance records for the period.
    2. Determine effective salary rate.
    3. Calculate based on salary method (HOURLY / DAILY_WAGE / MONTHLY).
    4. Apply line items from standard deductions (none seeded — configured per company).
    5. Build calculation_breakdown snapshot.
    """
    start_date = period.start_date
    end_date = period.end_date

    # ── Attendance data ──────────────────────────────────────────────────────
    att_records = AttendanceRecord.objects.filter(
        employee=employee,
        work_date__gte=start_date,
        work_date__lte=end_date,
    ).order_by("work_date")

    worked_hours = Decimal("0.0000")
    regular_hours = Decimal("0.0000")
    overtime_hours = Decimal("0.0000")
    payable_days = Decimal("0.0000")
    unpaid_leave_days = Decimal("0.0000")
    paid_leave_days = Decimal("0.0000")
    absent_days = Decimal("0.0000")
    has_incomplete = False

    attendance_log = []

    for rec in att_records:
        wh = rec.net_working_hours or Decimal("0.0000")
        rh = rec.regular_hours or Decimal("0.0000")
        oh = rec.overtime_hours or Decimal("0.0000")
        status = rec.status

        attendance_log.append({
            "date": str(rec.work_date),
            "status": status,
            "net_hours": str(wh),
            "regular_hours": str(rh),
            "overtime_hours": str(oh),
            "is_late": rec.is_late,
        })

        if status == AttendanceStatus.INCOMPLETE:
            has_incomplete = True
            # Incomplete records contribute zero hours but flag the statement
            continue
        elif status == AttendanceStatus.PRESENT:
            worked_hours += wh
            regular_hours += rh
            overtime_hours += oh
            payable_days += Decimal("1")
        elif status == AttendanceStatus.HALF_DAY:
            worked_hours += wh
            regular_hours += rh
            overtime_hours += oh
            payable_days += Decimal("0.5")
        elif status == AttendanceStatus.PAID_LEAVE:
            paid_leave_days += Decimal("1")
            payable_days += Decimal("1")  # Paid leave is payable
        elif status == AttendanceStatus.UNPAID_LEAVE:
            unpaid_leave_days += Decimal("1")
        elif status == AttendanceStatus.ABSENT:
            absent_days += Decimal("1")
        elif status in (AttendanceStatus.WEEKLY_OFF, AttendanceStatus.HOLIDAY):
            # Weekly off and holidays are not counted as payable unless configured
            pass

    # ── Effective rate ───────────────────────────────────────────────────────
    effective_rate_obj = get_effective_rate(employee, end_date)
    salary_method = effective_rate_obj.salary_calculation_method
    base_rate = Decimal(str(effective_rate_obj.base_rate))

    # Overtime rate determination
    if effective_rate_obj.overtime_rate:
        ot_rate = Decimal(str(effective_rate_obj.overtime_rate))
    else:
        # Default: base hourly rate × company multiplier
        if salary_method == SalaryMethod.MONTHLY:
            daily = base_rate / settings_obj.standard_daily_hours / Decimal("30")
            hourly_equiv = daily / settings_obj.standard_daily_hours
        elif salary_method == SalaryMethod.DAILY_WAGE:
            hourly_equiv = base_rate / settings_obj.standard_daily_hours
        else:
            hourly_equiv = base_rate  # HOURLY

        ot_rate = (hourly_equiv * settings_obj.overtime_rate_multiplier).quantize(
            FOUR_DP, rounding=ROUND_HALF_UP
        )

    # ── Pay calculation per salary method ────────────────────────────────────
    if salary_method == SalaryMethod.HOURLY:
        base_pay = (regular_hours * base_rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        overtime_pay = (
            (overtime_hours * ot_rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            if employee.overtime_eligible else Decimal("0.00")
        )
        scheduled_hours = settings_obj.standard_daily_hours * Decimal(str(period.duration_days))

    elif salary_method == SalaryMethod.DAILY_WAGE:
        # Pay per payable day at daily rate; paid leave counts as payable
        total_payable = payable_days
        base_pay = (total_payable * base_rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        overtime_pay = (
            (overtime_hours * ot_rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            if employee.overtime_eligible else Decimal("0.00")
        )
        scheduled_hours = settings_obj.standard_daily_hours * Decimal(str(period.duration_days))

    elif salary_method == SalaryMethod.MONTHLY:
        # Prorate monthly salary based on payable days vs. total calendar days in period
        total_period_days = Decimal(str(period.duration_days))
        proration_factor = (payable_days / total_period_days).quantize(
            FOUR_DP, rounding=ROUND_HALF_UP
        ) if total_period_days > 0 else Decimal("0.0000")

        # For monthly, base_rate is the full monthly salary
        # Adjust for period if not a full calendar month
        import calendar
        days_in_month = Decimal(str(
            calendar.monthrange(end_date.year, end_date.month)[1]
        ))
        period_fraction = total_period_days / days_in_month

        prorated_salary = (base_rate * period_fraction * proration_factor).quantize(
            TWO_DP, rounding=ROUND_HALF_UP
        )
        base_pay = prorated_salary
        overtime_pay = (
            (overtime_hours * ot_rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            if employee.overtime_eligible else Decimal("0.00")
        )
        scheduled_hours = settings_obj.standard_daily_hours * total_period_days

    else:
        base_pay = Decimal("0.00")
        overtime_pay = Decimal("0.00")
        scheduled_hours = Decimal("0.0000")

    # ── Totals ───────────────────────────────────────────────────────────────
    total_allowances = Decimal("0.00")
    total_bonuses = Decimal("0.00")
    total_deductions = Decimal("0.00")
    gross_pay = (base_pay + overtime_pay + total_allowances + total_bonuses).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    net_pay = (gross_pay - total_deductions).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    # ── Calculation snapshot ─────────────────────────────────────────────────
    breakdown = {
        "period": {"start": str(start_date), "end": str(end_date), "days": str(period.duration_days)},
        "salary_method": salary_method,
        "base_rate": str(base_rate),
        "ot_rate": str(ot_rate),
        "hours": {
            "scheduled": str(scheduled_hours.quantize(TWO_DP)),
            "worked": str(worked_hours.quantize(TWO_DP)),
            "regular": str(regular_hours.quantize(TWO_DP)),
            "overtime": str(overtime_hours.quantize(TWO_DP)),
        },
        "days": {
            "payable": str(payable_days),
            "paid_leave": str(paid_leave_days),
            "unpaid_leave": str(unpaid_leave_days),
            "absent": str(absent_days),
        },
        "pay": {
            "base": str(base_pay),
            "overtime": str(overtime_pay),
            "allowances": str(total_allowances),
            "bonuses": str(total_bonuses),
            "deductions": str(total_deductions),
            "gross": str(gross_pay),
            "net": str(net_pay),
        },
        "has_incomplete_records": has_incomplete,
        "attendance": attendance_log,
        "generated_by": str(requested_by),
    }

    statement = PayrollStatement(
        payroll_period=period,
        employee=employee,
        salary_method=salary_method,
        base_rate=base_rate,
        overtime_rate=ot_rate,
        scheduled_hours=scheduled_hours.quantize(FOUR_DP, rounding=ROUND_HALF_UP),
        worked_hours=worked_hours,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        payable_days=payable_days,
        unpaid_leave_days=unpaid_leave_days,
        paid_leave_days=paid_leave_days,
        absent_days=absent_days,
        base_pay=base_pay,
        overtime_pay=overtime_pay,
        total_allowances=total_allowances,
        total_bonuses=total_bonuses,
        total_deductions=total_deductions,
        gross_pay=gross_pay,
        net_pay=net_pay,
        status=PayrollStatus.DRAFT,
        calculation_breakdown=breakdown,
    )
    return statement


# ─── Generate Full Payroll Period ───────────────────────────────────────────────

@transaction.atomic
def generate_payroll_period(
    cycle_type: str,
    start_date: datetime.date,
    end_date: datetime.date,
    requested_by,
    notes: str = "",
    department: Optional[Department] = None,
) -> PayrollPeriod:
    """
    Generate payroll statements for active employees (optionally filtered by department)
    for the specified period.
    Wrapped in a database transaction — all or nothing.
    """
    settings_obj = CompanySettings.get()

    # Validate period
    period = PayrollPeriod(
        cycle_type=cycle_type,
        start_date=start_date,
        end_date=end_date,
        department=department,
        generated_by=requested_by,
        notes=notes,
    )
    period.validate_no_overlap()
    period.save()

    # Filter active employees (all or specific department)
    employees = Employee.objects.filter(employment_status="ACTIVE")
    if department:
        employees = employees.filter(department=department)

    if not employees.exists():
        dept_label = department.name if department else "the company"
        raise ValueError(f"No active employees found in {dept_label} to generate payroll for.")

    errors = []

    for employee in employees:
        try:
            statement = calculate_employee_payroll(employee, period, settings_obj, requested_by)
            statement.save()
        except Exception as exc:
            logger.error("Payroll calc failed for emp=%s period=%s: %s", employee.employee_id, period.pk, exc)
            errors.append({"employee_id": employee.employee_id, "error": str(exc)})

    if errors:
        logger.warning("Payroll generated with %d errors: %s", len(errors), errors)

    period.status = PayrollStatus.DRAFT
    period.save(update_fields=["status"])

    return period


@transaction.atomic
def finalize_payroll_period(period: PayrollPeriod, finalized_by) -> PayrollPeriod:
    """
    Finalize all REVIEWED statements in a period.
    Prevents double-finalization through row-level locking (select_for_update).
    Attendance records are locked.
    """
    # Row lock to prevent concurrent finalization
    period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)

    if period.status == PayrollStatus.FINALIZED:
        raise ValueError("Payroll period is already finalized.")
    if period.status != PayrollStatus.REVIEWED:
        raise ValueError("Payroll must be in REVIEWED status before finalization.")

    statements = PayrollStatement.objects.filter(payroll_period=period)
    for stmt in statements:
        stmt.finalize(by_user=finalized_by)

    period.status = PayrollStatus.FINALIZED
    period.finalized_by = finalized_by
    period.finalized_at = timezone.now()
    period.save()

    return period

"""
Thamarayyath Employee Portal — Attendance Views.
"""

import datetime
import logging
from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from accounts.permissions import AnyRoleMixin, AccountantOrSuperadminMixin, SuperadminRequiredMixin
from accounts.models import CompanySettings
from audit.services import audit_log
from employees.models import Employee, Department
from .forms import AttendanceMarkForm, AttendanceCorrectionForm, AttendanceDateRangeFilterForm, HolidayForm
from .models import AttendanceRecord, AttendanceCorrectionLog, AttendanceStatus, AttendanceEntryMethod, Holiday

logger = logging.getLogger("portal")


# ─── Daily Attendance Dashboard ─────────────────────────────────────────────────

class DailyAttendanceDashboard(AnyRoleMixin, View):
    template_name = "attendance/daily_dashboard.html"

    def get(self, request):
        date_str = request.GET.get("date", "")
        try:
            work_date = datetime.date.fromisoformat(date_str) if date_str else timezone.localdate()
        except ValueError:
            work_date = timezone.localdate()

        active_employees = (
            Employee.objects
            .filter(employment_status="ACTIVE")
            .select_related("department", "assigned_shift")
            .order_by("employee_id")
        )

        records_qs = (
            AttendanceRecord.objects
            .filter(work_date=work_date)
            .select_related("employee", "employee__department")
            .order_by("employee__employee_id")
        )
        records_by_emp = {rec.employee_id: rec for rec in records_qs}

        # Build roster entries for all active employees
        roster_items = []
        for emp in active_employees:
            rec = records_by_emp.get(emp.id)
            roster_items.append({
                "employee": emp,
                "record": rec,
                "is_marked": bool(rec),
            })

        summary = {
            "total_active": active_employees.count(),
            "unmarked": active_employees.count() - len(records_by_emp),
            "present": records_qs.filter(status=AttendanceStatus.PRESENT).count(),
            "absent": records_qs.filter(status=AttendanceStatus.ABSENT).count(),
            "half_day": records_qs.filter(status=AttendanceStatus.HALF_DAY).count(),
            "incomplete": records_qs.filter(status=AttendanceStatus.INCOMPLETE).count(),
            "on_leave": records_qs.filter(status__in=[
                AttendanceStatus.PAID_LEAVE, AttendanceStatus.UNPAID_LEAVE
            ]).count(),
            "late": records_qs.filter(is_late=True).count(),
        }

        return render(request, self.template_name, {
            "roster_items": roster_items,
            "records": records_qs,
            "work_date": work_date,
            "summary": summary,
            "today": timezone.localdate(),
        })


class QuickAttendanceMarkView(AccountantOrSuperadminMixin, View):
    """
    1-Click Quick Attendance Marker:
    Directly marks an employee as Present (or Clock Out) with a single click from outside.
    """

    def post(self, request):
        work_date_str = request.POST.get("work_date", "")
        try:
            work_date = datetime.date.fromisoformat(work_date_str) if work_date_str else timezone.localdate()
        except ValueError:
            work_date = timezone.localdate()

        action_type = request.POST.get("action_type", "mark_present")
        redirect_url = request.POST.get("next") or f"{redirect('attendance:daily_dashboard').url}?date={work_date}"
        settings_obj = CompanySettings.get()
        tz = timezone.get_current_timezone()

        if action_type == "bulk_all_pending":
            active_employees = Employee.objects.filter(employment_status="ACTIVE").select_related("assigned_shift")
            existing_ids = set(
                AttendanceRecord.objects.filter(work_date=work_date).values_list("employee_id", flat=True)
            )
            pending_employees = [e for e in active_employees if e.id not in existing_ids]

            created = 0
            with transaction.atomic():
                for emp in pending_employees:
                    shift = emp.assigned_shift
                    start_time = shift.start_time if shift else datetime.time(9, 0)
                    end_time = shift.end_time if shift else datetime.time(18, 0)
                    unpaid_break = shift.unpaid_break_minutes if shift else 60
                    is_overnight = shift.is_night_shift if shift else False

                    check_in_dt = timezone.make_aware(datetime.datetime.combine(work_date, start_time), tz)
                    check_out_date = work_date + datetime.timedelta(days=1) if is_overnight else work_date
                    check_out_dt = timezone.make_aware(datetime.datetime.combine(check_out_date, end_time), tz)

                    rec = AttendanceRecord(
                        employee=emp,
                        work_date=work_date,
                        check_in=check_in_dt,
                        check_out=check_out_dt,
                        break_duration_minutes=unpaid_break,
                        status=AttendanceStatus.PRESENT,
                        entry_method=AttendanceEntryMethod.MANUAL,
                        correction_reason="Quick-marked present via Daily Tracker",
                        created_by=request.user,
                        last_modified_by=request.user,
                    )
                    rec.calculate_hours(settings_obj.daily_overtime_threshold_hours)
                    rec.calculate_late_flag(settings_obj.late_grace_period_minutes)
                    rec.save()
                    created += 1

                audit_log(
                    actor=request.user, action="ATTENDANCE_MARK",
                    target_model="AttendanceRecord", target_id="bulk",
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"count": created, "work_date": str(work_date)},
                )
            messages.success(request, f"✓ Quick-marked {created} pending employees as Present for {work_date}.")
            return redirect(redirect_url)

        employee_pk = request.POST.get("employee_pk")
        if not employee_pk:
            messages.error(request, "Employee not specified.")
            return redirect(redirect_url)

        employee = get_object_or_404(Employee, pk=employee_pk)
        record = AttendanceRecord.objects.filter(employee=employee, work_date=work_date).first()

        if action_type == "clock_out" and record:
            if record.is_locked_by_payroll:
                messages.error(request, "Cannot clock out: record is locked by finalized payroll.")
                return redirect(redirect_url)
            with transaction.atomic():
                record.check_out = timezone.now()
                record.status = AttendanceStatus.PRESENT
                record.last_modified_by = request.user
                record.calculate_hours(settings_obj.daily_overtime_threshold_hours)
                record.save()
                audit_log(
                    actor=request.user, action="ATTENDANCE_MARK",
                    target_model="AttendanceRecord", target_id=str(record.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": employee.employee_id, "action": "clock_out"},
                )
            messages.success(request, f"Clocked out {employee.full_name} ({record.net_working_hours} hrs logged).")
            return redirect(redirect_url)

        if record:
            if record.status == AttendanceStatus.PRESENT:
                messages.info(request, f"{employee.full_name} is already marked Present for {work_date}.")
                return redirect(redirect_url)
            elif record.status == AttendanceStatus.INCOMPLETE:
                with transaction.atomic():
                    shift = employee.assigned_shift
                    end_time = shift.end_time if shift else datetime.time(18, 0)
                    is_overnight = shift.is_night_shift if shift else False
                    check_out_date = work_date + datetime.timedelta(days=1) if is_overnight else work_date
                    record.check_out = timezone.make_aware(datetime.datetime.combine(check_out_date, end_time), tz)
                    record.status = AttendanceStatus.PRESENT
                    record.last_modified_by = request.user
                    record.calculate_hours(settings_obj.daily_overtime_threshold_hours)
                    record.save()
                messages.success(request, f"Completed punch for {employee.full_name} as Present ({record.net_working_hours} hrs).")
                return redirect(redirect_url)

        with transaction.atomic():
            shift = employee.assigned_shift
            start_time = shift.start_time if shift else datetime.time(9, 0)
            end_time = shift.end_time if shift else datetime.time(18, 0)
            unpaid_break = shift.unpaid_break_minutes if shift else 60
            is_overnight = shift.is_night_shift if shift else False

            check_in_dt = timezone.make_aware(datetime.datetime.combine(work_date, start_time), tz)
            check_out_date = work_date + datetime.timedelta(days=1) if is_overnight else work_date
            check_out_dt = timezone.make_aware(datetime.datetime.combine(check_out_date, end_time), tz)

            new_rec = AttendanceRecord(
                employee=employee,
                work_date=work_date,
                check_in=check_in_dt,
                check_out=check_out_dt,
                break_duration_minutes=unpaid_break,
                status=AttendanceStatus.PRESENT,
                entry_method=AttendanceEntryMethod.MANUAL,
                correction_reason="Quick-marked present",
                created_by=request.user,
                last_modified_by=request.user,
            )
            new_rec.calculate_hours(settings_obj.daily_overtime_threshold_hours)
            new_rec.calculate_late_flag(settings_obj.late_grace_period_minutes)
            new_rec.save()

            audit_log(
                actor=request.user, action="ATTENDANCE_MARK",
                target_model="AttendanceRecord", target_id=str(new_rec.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"employee_id": employee.employee_id, "work_date": str(work_date), "method": "quick_mark"},
            )
        messages.success(request, f"✓ Quick-marked {employee.full_name} as Present ({new_rec.net_working_hours} hrs).")
        return redirect(redirect_url)


# ─── Attendance List ─────────────────────────────────────────────────────────────

class AttendanceListView(AnyRoleMixin, View):
    template_name = "attendance/attendance_list.html"

    def get(self, request):
        form = AttendanceDateRangeFilterForm(request.GET)
        qs = AttendanceRecord.objects.select_related(
            "employee", "employee__department", "created_by"
        ).order_by("-work_date", "employee__employee_id")

        if form.is_valid():
            if form.cleaned_data.get("employee"):
                qs = qs.filter(employee=form.cleaned_data["employee"])
            if form.cleaned_data.get("department"):
                qs = qs.filter(employee__department=form.cleaned_data["department"])
            if form.cleaned_data.get("date_from"):
                qs = qs.filter(work_date__gte=form.cleaned_data["date_from"])
            if form.cleaned_data.get("date_to"):
                qs = qs.filter(work_date__lte=form.cleaned_data["date_to"])
            if form.cleaned_data.get("status"):
                qs = qs.filter(status=form.cleaned_data["status"])

        from django.core.paginator import Paginator
        paginator = Paginator(qs, 50)
        page = paginator.get_page(request.GET.get("page"))
        return render(request, self.template_name, {"form": form, "page_obj": page})


# ─── Mark Attendance (Accountant) ───────────────────────────────────────────────

class AttendanceMarkView(AccountantOrSuperadminMixin, View):
    template_name = "attendance/attendance_mark.html"

    def get(self, request, employee_pk=None):
        employees = Employee.objects.filter(employment_status="ACTIVE").order_by("employee_id")
        selected_employee = None
        if employee_pk:
            selected_employee = get_object_or_404(Employee, pk=employee_pk)
        date_param = request.GET.get("date")
        try:
            initial_date = datetime.date.fromisoformat(date_param) if date_param else timezone.localdate()
        except ValueError:
            initial_date = timezone.localdate()
        form = AttendanceMarkForm(initial={"work_date": initial_date})
        return render(request, self.template_name, {
            "form": form,
            "employees": employees,
            "selected_employee": selected_employee,
        })

    def post(self, request, employee_pk=None):
        employee = get_object_or_404(Employee, pk=request.POST.get("employee_pk", employee_pk))
        form = AttendanceMarkForm(request.POST)

        if form.is_valid():
            work_date = form.cleaned_data["work_date"]
            check_in_dt = form.cleaned_data.get("_check_in_dt")
            check_out_dt = form.cleaned_data.get("_check_out_dt")
            status = form.cleaned_data["status"]

            # Duplicate check
            if AttendanceRecord.objects.filter(employee=employee, work_date=work_date).exists():
                form.add_error("work_date", f"Attendance already exists for {employee.employee_id} on {work_date}.")
                return render(request, self.template_name, {"form": form, "selected_employee": employee,
                                                            "employees": Employee.objects.filter(employment_status="ACTIVE")})

            settings_obj = CompanySettings.get()
            with transaction.atomic():
                record = AttendanceRecord(
                    employee=employee,
                    work_date=work_date,
                    check_in=check_in_dt,
                    check_out=check_out_dt,
                    break_duration_minutes=form.cleaned_data["break_duration_minutes"],
                    status=status,
                    entry_method=AttendanceEntryMethod.MANUAL,
                    correction_reason=form.cleaned_data.get("correction_reason", ""),
                    created_by=request.user,
                    last_modified_by=request.user,
                )
                record.calculate_hours(
                    daily_threshold_hours=settings_obj.daily_overtime_threshold_hours
                )
                record.calculate_late_flag(grace_period_minutes=settings_obj.late_grace_period_minutes)

                # Custom overtime hours override if accountant specified
                custom_ot = form.cleaned_data.get("overtime_hours")
                if custom_ot is not None:
                    record.overtime_hours = custom_ot
                    if record.net_working_hours > 0:
                        record.regular_hours = max(Decimal("0.0000"), record.net_working_hours - custom_ot)

                if check_in_dt and not check_out_dt:
                    record.status = AttendanceStatus.INCOMPLETE

                record.save()
                audit_log(
                    actor=request.user, action="ATTENDANCE_MARK",
                    target_model="AttendanceRecord", target_id=str(record.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "employee_id": employee.employee_id,
                        "work_date": str(work_date),
                        "status": status,
                    },
                )
            messages.success(request, f"Attendance recorded for {employee.full_name} on {work_date}.")
            return redirect("attendance:daily_dashboard")

        return render(request, self.template_name, {
            "form": form,
            "selected_employee": employee,
            "employees": Employee.objects.filter(employment_status="ACTIVE"),
        })


# ─── Attendance Correction ──────────────────────────────────────────────────────

class AttendanceCorrectionView(AccountantOrSuperadminMixin, View):
    template_name = "attendance/attendance_correct.html"

    def get(self, request, pk):
        record = get_object_or_404(AttendanceRecord, pk=pk)
        if record.is_locked_by_payroll:
            messages.error(
                request,
                "This attendance record is locked by a finalized payroll. "
                "A payroll reversal or Superadmin authorization is required to correct it."
            )
            return redirect("attendance:attendance_detail", pk=pk)
        form = AttendanceCorrectionForm(instance=record)
        return render(request, self.template_name, {"form": form, "record": record})

    def post(self, request, pk):
        record = get_object_or_404(AttendanceRecord, pk=pk)
        if record.is_locked_by_payroll:
            raise PermissionDenied("Correction blocked: payroll finalized.")

        form = AttendanceCorrectionForm(request.POST, instance=record)
        if form.is_valid():
            # Capture old values before saving
            old_values = {
                "check_in": str(record.check_in),
                "check_out": str(record.check_out),
                "status": record.status,
                "break_duration_minutes": record.break_duration_minutes,
                "net_working_hours": str(record.net_working_hours),
            }
            settings_obj = CompanySettings.get()
            with transaction.atomic():
                corrected = form.save(commit=False)
                corrected.entry_method = AttendanceEntryMethod.CORRECTION
                corrected.last_modified_by = request.user
                corrected.calculate_hours(settings_obj.daily_overtime_threshold_hours)
                corrected.calculate_late_flag(settings_obj.late_grace_period_minutes)

                custom_ot = form.cleaned_data.get("overtime_hours")
                if custom_ot is not None:
                    corrected.overtime_hours = custom_ot
                    if corrected.net_working_hours > 0:
                        corrected.regular_hours = max(Decimal("0.0000"), corrected.net_working_hours - custom_ot)

                corrected.save()

                new_values = {
                    "check_in": str(corrected.check_in),
                    "check_out": str(corrected.check_out),
                    "status": corrected.status,
                    "break_duration_minutes": corrected.break_duration_minutes,
                    "net_working_hours": str(corrected.net_working_hours),
                }
                AttendanceCorrectionLog.objects.create(
                    attendance_record=corrected,
                    modified_by=request.user,
                    old_values=old_values,
                    new_values=new_values,
                    reason=form.cleaned_data["correction_reason"],
                )
                audit_log(
                    actor=request.user, action="ATTENDANCE_CORRECT",
                    target_model="AttendanceRecord", target_id=str(corrected.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "employee_id": corrected.employee.employee_id,
                        "work_date": str(corrected.work_date),
                        "reason": form.cleaned_data["correction_reason"],
                    },
                )
            messages.success(request, "Attendance corrected. Correction log entry created.")
            return redirect("attendance:attendance_detail", pk=corrected.pk)

        return render(request, self.template_name, {"form": form, "record": record})


class AttendanceDetailView(AnyRoleMixin, View):
    template_name = "attendance/attendance_detail.html"

    def get(self, request, pk):
        record = get_object_or_404(
            AttendanceRecord.objects.select_related(
                "employee", "created_by", "last_modified_by"
            ), pk=pk
        )
        correction_logs = record.correction_logs.select_related("modified_by").all()
        return render(request, self.template_name, {
            "record": record,
            "correction_logs": correction_logs,
        })


# ─── Holiday Management ─────────────────────────────────────────────────────────

class HolidayListView(AnyRoleMixin, ListView):
    model = Holiday
    template_name = "attendance/holiday_list.html"
    context_object_name = "holidays"
    queryset = Holiday.objects.order_by("date")


class HolidayCreateView(AccountantOrSuperadminMixin, View):
    template_name = "attendance/holiday_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": HolidayForm()})

    def post(self, request):
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save(commit=False)
            holiday.created_by = request.user
            holiday.save()
            audit_log(
                actor=request.user, action="HOLIDAY_CREATE",
                target_model="Holiday", target_id=str(holiday.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"name": holiday.name, "date": str(holiday.date)},
            )
            messages.success(request, f"Holiday '{holiday.name}' added.")
            return redirect("attendance:holiday_list")
        return render(request, self.template_name, {"form": form})


class HolidayDeleteView(AccountantOrSuperadminMixin, View):
    template_name = "attendance/holiday_confirm_delete.html"

    def get(self, request, pk):
        holiday = get_object_or_404(Holiday, pk=pk)
        return render(request, self.template_name, {"holiday": holiday})

    def post(self, request, pk):
        holiday = get_object_or_404(Holiday, pk=pk)
        holiday_name = holiday.name
        holiday_date = str(holiday.date)
        with transaction.atomic():
            holiday.delete()
            audit_log(
                actor=request.user, action="HOLIDAY_DELETE",
                target_model="Holiday", target_id=str(pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"name": holiday_name, "date": holiday_date},
            )
        messages.success(request, f"Holiday '{holiday_name}' ({holiday_date}) deleted successfully.")
        return redirect("attendance:holiday_list")


# ─── Leave Management ───────────────────────────────────────────────────────────

class LeaveListView(AnyRoleMixin, View):
    template_name = "attendance/leave_list.html"

    def get(self, request):
        from .models import LeaveRecord
        leaves = LeaveRecord.objects.select_related("employee", "approved_by").order_by("-start_date")
        emp_filter = request.GET.get("employee")
        if emp_filter:
            leaves = leaves.filter(employee_id=emp_filter)
        return render(request, self.template_name, {
            "leaves": leaves,
            "can_manage": not request.user.is_owner,
        })


class LeaveCreateView(AccountantOrSuperadminMixin, View):
    template_name = "attendance/leave_form.html"

    def get(self, request):
        from .forms import LeaveRecordForm
        return render(request, self.template_name, {"form": LeaveRecordForm()})

    def post(self, request):
        from .forms import LeaveRecordForm
        form = LeaveRecordForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            if leave.status == "APPROVED":
                leave.approved_by = request.user
            leave.save()
            audit_log(
                actor=request.user, action="ATTENDANCE_MARK",
                target_model="LeaveRecord", target_id=str(leave.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"employee": leave.employee.employee_id, "type": leave.leave_type},
            )
            messages.success(request, f"Leave recorded for {leave.employee.full_name}.")
            return redirect("attendance:leave_list")
        return render(request, self.template_name, {"form": form})


class LeaveStatusUpdateView(AccountantOrSuperadminMixin, View):
    def post(self, request, pk):
        from .models import LeaveRecord
        leave = get_object_or_404(LeaveRecord, pk=pk)
        new_status = request.POST.get("status")
        if new_status in ("APPROVED", "REJECTED", "PENDING"):
            leave.status = new_status
            if new_status == "APPROVED":
                leave.approved_by = request.user
            leave.save()
            messages.success(request, f"Leave status updated to {new_status}.")
        return redirect("attendance:leave_list")


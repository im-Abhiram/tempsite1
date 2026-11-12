"""
Thamarayyath Employee Portal — Dashboard Views.
Provides specialized, role-tailored dashboards for Superadmin, Accountant, and Owner.
"""

import datetime
import json
import logging
from decimal import Decimal
from django.db.models import Sum, Q, Count
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View

from accounts.models import CustomUser, Role, CompanySettings
from accounts.permissions import (
    AnyRoleMixin, SuperadminRequiredMixin, AccountantRequiredMixin, RoleRequiredMixin
)
from attendance.models import AttendanceRecord, AttendanceStatus, AttendanceCorrectionLog, LeaveRecord
from audit.models import AuditLog
from core.services import get_storage_usage
from employees.models import Employee, EmploymentStatus
from payroll.models import PayrollPeriod, PayrollStatement, PayrollStatus

logger = logging.getLogger("portal")


class DashboardRouterView(AnyRoleMixin, View):
    """
    Central dashboard entrypoint.
    Inspects user role server-side and routes to the appropriate role dashboard.
    """
    def get(self, request):
        if request.user.is_superadmin:
            return SuperadminDashboardView().get(request)
        elif request.user.is_office_admin:
            return OfficeAdminDashboardView().get(request)
        else:
            return OwnerDashboardView().get(request)


class SuperadminDashboardView(SuperadminRequiredMixin, View):
    """
    Superadmin Dashboard:
    Full system statistics, account counts, today's attendance, recent audit logs,
    live storage usage metrics, and Chart.js attendance trends.
    """
    template_name = "dashboard/superadmin_dashboard.html"

    def get(self, request):
        today = timezone.localdate()
        total_emp = Employee.objects.count()
        active_emp = Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).count()
        inactive_emp = total_emp - active_emp

        office_admin_count = CustomUser.objects.filter(role__in=[Role.OFFICE_ADMIN, "ACCOUNTANT"]).count()
        owner_count = CustomUser.objects.filter(role=Role.OWNER).count()

        # Today's attendance
        today_records = AttendanceRecord.objects.filter(work_date=today)
        today_present = today_records.filter(status=AttendanceStatus.PRESENT).count()
        today_half_day = today_records.filter(status=AttendanceStatus.HALF_DAY).count()
        today_leave = today_records.filter(status__in=[AttendanceStatus.PAID_LEAVE, AttendanceStatus.UNPAID_LEAVE]).count()
        today_incomplete = today_records.filter(status=AttendanceStatus.INCOMPLETE).count()
        today_absent = today_records.filter(status=AttendanceStatus.ABSENT).count()

        # Recent audit events
        recent_events = AuditLog.objects.select_related("actor").order_by("-timestamp")[:10]
        recent_corrections = AttendanceCorrectionLog.objects.select_related("attendance_record__employee", "modified_by").order_by("-timestamp")[:5]

        # Latest payroll activity
        latest_payroll = PayrollPeriod.objects.order_by("-start_date")[:5]

        # Storage usage info
        storage_info = get_storage_usage()

        # Past 14 days attendance trend for Chart.js
        chart_labels = []
        chart_present = []
        chart_absent = []
        chart_leave = []

        start_chart_date = today - datetime.timedelta(days=13)
        history_records = AttendanceRecord.objects.filter(
            work_date__gte=start_chart_date, work_date__lte=today
        ).values("work_date", "status")

        counts_by_date = {}
        for r in history_records:
            d = r["work_date"]
            if d not in counts_by_date:
                counts_by_date[d] = {"present": 0, "absent": 0, "leave": 0}
            st = r["status"]
            if st in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY):
                counts_by_date[d]["present"] += 1
            elif st == AttendanceStatus.ABSENT:
                counts_by_date[d]["absent"] += 1
            elif st in (AttendanceStatus.PAID_LEAVE, AttendanceStatus.UNPAID_LEAVE):
                counts_by_date[d]["leave"] += 1

        for i in range(14):
            day = start_chart_date + datetime.timedelta(days=i)
            chart_labels.append(day.strftime("%d %b"))
            day_data = counts_by_date.get(day, {"present": 0, "absent": 0, "leave": 0})
            chart_present.append(day_data["present"])
            chart_absent.append(day_data["absent"])
            chart_leave.append(day_data["leave"])

        context = {
            "total_employees": total_emp,
            "active_employees": active_emp,
            "inactive_employees": inactive_emp,
            "accountant_count": office_admin_count,
            "office_admin_count": office_admin_count,
            "owner_count": owner_count,
            "today_present": today_present,
            "today_half_day": today_half_day,
            "today_leave": today_leave,
            "today_incomplete": today_incomplete,
            "today_absent": today_absent,
            "recent_events": recent_events,
            "recent_corrections": recent_corrections,
            "latest_payroll": latest_payroll,
            "storage": storage_info,
            "chart_labels": json.dumps(chart_labels),
            "chart_present": json.dumps(chart_present),
            "chart_absent": json.dumps(chart_absent),
            "chart_leave": json.dumps(chart_leave),
            "today": today,
        }
        return render(request, self.template_name, context)


class OfficeAdminDashboardView(AccountantRequiredMixin, View):
    """
    Office Administration Dashboard:
    Daily attendance operations hub, hours logged, overtime totals,
    payroll periods awaiting review, and recent roster changes.
    """
    template_name = "dashboard/accountant_dashboard.html"

    def get(self, request):
        today = timezone.localdate()
        active_emp_qs = Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE)
        total_active = active_emp_qs.count()

        today_records = AttendanceRecord.objects.filter(work_date=today)
        present_today = today_records.filter(status=AttendanceStatus.PRESENT).count()
        half_day_today = today_records.filter(status=AttendanceStatus.HALF_DAY).count()
        absent_today = today_records.filter(status=AttendanceStatus.ABSENT).count()
        leave_today = today_records.filter(status__in=[AttendanceStatus.PAID_LEAVE, AttendanceStatus.UNPAID_LEAVE]).count()
        incomplete_today = today_records.filter(status=AttendanceStatus.INCOMPLETE).count()

        unmarked_today = max(0, total_active - (present_today + half_day_today + absent_today + leave_today + incomplete_today))

        # Total working hours today
        today_hours_agg = today_records.aggregate(
            total_net=Sum("net_working_hours"),
            total_ot=Sum("overtime_hours"),
        )
        total_working_hours_today = today_hours_agg["total_net"] or Decimal("0.00")
        total_ot_today = today_hours_agg["total_ot"] or Decimal("0.00")

        # Overtime summary for past 30 days
        thirty_days_ago = today - datetime.timedelta(days=30)
        overtime_30d = AttendanceRecord.objects.filter(
            work_date__gte=thirty_days_ago, work_date__lte=today
        ).aggregate(total_ot=Sum("overtime_hours"))["total_ot"] or Decimal("0.00")

        # Payroll awaiting review or finalization
        payroll_pending = PayrollPeriod.objects.filter(
            status__in=[PayrollStatus.DRAFT, PayrollStatus.REVIEWED]
        ).order_by("-start_date")

        # Recent employee updates
        recent_employees = Employee.objects.order_by("-updated_at")[:6]

        # Past 14 days attendance trend for Office Admin chart
        chart_labels = []
        chart_present = []
        chart_absent = []
        chart_leave = []

        start_chart_date = today - datetime.timedelta(days=13)
        history_records = AttendanceRecord.objects.filter(
            work_date__gte=start_chart_date, work_date__lte=today
        ).values("work_date", "status")

        counts_by_date = {}
        for r in history_records:
            d = r["work_date"]
            if d not in counts_by_date:
                counts_by_date[d] = {"present": 0, "absent": 0, "leave": 0}
            st = r["status"]
            if st in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY):
                counts_by_date[d]["present"] += 1
            elif st == AttendanceStatus.ABSENT:
                counts_by_date[d]["absent"] += 1
            elif st in (AttendanceStatus.PAID_LEAVE, AttendanceStatus.UNPAID_LEAVE):
                counts_by_date[d]["leave"] += 1

        for i in range(14):
            day = start_chart_date + datetime.timedelta(days=i)
            chart_labels.append(day.strftime("%d %b"))
            day_data = counts_by_date.get(day, {"present": 0, "absent": 0, "leave": 0})
            chart_present.append(day_data["present"])
            chart_absent.append(day_data["absent"])
            chart_leave.append(day_data["leave"])

        context = {
            "total_active": total_active,
            "present_today": present_today,
            "half_day_today": half_day_today,
            "absent_today": absent_today,
            "leave_today": leave_today,
            "incomplete_today": incomplete_today,
            "unmarked_today": unmarked_today,
            "total_working_hours_today": total_working_hours_today,
            "total_ot_today": total_ot_today,
            "overtime_30d": overtime_30d,
            "payroll_pending": payroll_pending,
            "recent_employees": recent_employees,
            "chart_labels": json.dumps(chart_labels),
            "chart_present": json.dumps(chart_present),
            "chart_absent": json.dumps(chart_absent),
            "chart_leave": json.dumps(chart_leave),
            "today": today,
        }
        return render(request, self.template_name, context)


AccountantDashboardView = OfficeAdminDashboardView


class OwnerDashboardView(RoleRequiredMixin, View):
    """
    Owner Dashboard:
    Strictly read-only executive overview with attendance percentage, monthly working hours,
    overtime outlay, finalized salary summary, and Chart.js visual trends.
    """
    required_roles = [Role.OWNER, Role.SUPERADMIN]
    template_name = "dashboard/owner_dashboard.html"

    def get(self, request):
        today = timezone.localdate()
        active_emp_count = Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).count()

        today_records = AttendanceRecord.objects.filter(work_date=today)
        present_today = today_records.filter(status=AttendanceStatus.PRESENT).count()
        half_day_today = today_records.filter(status=AttendanceStatus.HALF_DAY).count()
        total_attended = present_today + (half_day_today * Decimal("0.5"))

        attendance_pct = (
            round((float(total_attended) / active_emp_count) * 100, 1)
            if active_emp_count > 0 else 0.0
        )

        # Current month aggregates
        month_start = today.replace(day=1)
        month_records = AttendanceRecord.objects.filter(
            work_date__gte=month_start, work_date__lte=today
        )
        month_agg = month_records.aggregate(
            total_net=Sum("net_working_hours"),
            total_ot=Sum("overtime_hours"),
        )
        total_working_hours_month = month_agg["total_net"] or Decimal("0.00")
        total_ot_month = month_agg["total_ot"] or Decimal("0.00")

        # Latest finalized payroll overview
        latest_finalized = PayrollPeriod.objects.filter(
            status=PayrollStatus.FINALIZED
        ).order_by("-end_date").first()

        # Monthly attendance trend (Past 30 days) for Chart.js
        start_chart_date = today - datetime.timedelta(days=29)
        chart_records = AttendanceRecord.objects.filter(
            work_date__gte=start_chart_date, work_date__lte=today
        ).values("work_date", "status")

        counts_by_date = {}
        for r in chart_records:
            d = r["work_date"]
            if d not in counts_by_date:
                counts_by_date[d] = {"present": 0, "absent": 0}
            if r["status"] in (AttendanceStatus.PRESENT, AttendanceStatus.HALF_DAY):
                counts_by_date[d]["present"] += 1
            else:
                counts_by_date[d]["absent"] += 1

        chart_labels = []
        chart_present = []
        chart_absent = []
        for i in range(30):
            day = start_chart_date + datetime.timedelta(days=i)
            chart_labels.append(day.strftime("%d %b"))
            day_data = counts_by_date.get(day, {"present": 0, "absent": 0})
            chart_present.append(day_data["present"])
            chart_absent.append(day_data["absent"])

        context = {
            "total_employees": active_emp_count,
            "present_today": present_today,
            "attendance_percentage": attendance_pct,
            "total_working_hours_month": total_working_hours_month,
            "total_ot_month": total_ot_month,
            "latest_finalized": latest_finalized,
            "chart_labels": json.dumps(chart_labels),
            "chart_present": json.dumps(chart_present),
            "chart_absent": json.dumps(chart_absent),
            "today": today,
            "is_read_only": True,
        }
        return render(request, self.template_name, context)


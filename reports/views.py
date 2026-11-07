"""
Thamarayyath Employee Portal — Reports Views.
Comprehensive reporting engine with CSV, Excel (openpyxl) and PDF (ReportLab) exports.
All exports enforce server-side role gating, audit logging, and formula injection sanitization.
"""

import csv
import datetime
import io
import logging
from decimal import Decimal
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views import View

from accounts.models import CompanySettings, PayrollCycle
from accounts.permissions import AnyRoleMixin, AccountantOrSuperadminMixin, SuperadminRequiredMixin
from attendance.models import AttendanceRecord, AttendanceStatus, LeaveRecord
from audit.services import audit_log
from employees.models import Employee, Department
from payroll.models import PayrollPeriod, PayrollStatement, PayrollStatus

logger = logging.getLogger("portal")

SAFE_STR = lambda v: ("'" + str(v)) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else str(v)


def _check_export_permission(request, is_sensitive_salary=False):
    """
    Enforces that Owners can only export if allow_owner_export is enabled.
    Sensitive salary reports are restricted to Superadmin and Accountant.
    """
    if is_sensitive_salary and request.user.is_owner:
        raise PermissionDenied("Access to sensitive salary export is restricted to Accountant and Superadmin.")
    if request.user.is_owner and not CompanySettings.get().allow_owner_export:
        raise PermissionDenied("Data exports are disabled for your role by company policy.")


# ─── Reports Dashboards ────────────────────────────────────────────────────────

class ReportsHubView(AnyRoleMixin, View):
    """Main Reports Directory."""
    template_name = "reports/reports_hub.html"

    def get(self, request):
        settings_obj = CompanySettings.get()
        return render(request, self.template_name, {
            "settings": settings_obj,
            "can_export": not request.user.is_owner or settings_obj.allow_owner_export,
            "is_owner": request.user.is_owner,
            "payroll_cycles": PayrollCycle.choices,
        })


class AttendanceReportsView(AnyRoleMixin, View):
    """Attendance & Hours Reports Dashboard."""
    template_name = "reports/attendance_reports.html"

    def get(self, request):
        employees = Employee.objects.filter(employment_status="ACTIVE").order_by("employee_id")
        departments = Department.objects.filter(is_active=True).order_by("name")
        today = timezone.localdate()
        return render(request, self.template_name, {
            "employees": employees,
            "departments": departments,
            "today": today,
            "can_export": not request.user.is_owner or CompanySettings.get().allow_owner_export,
        })


class SalaryReportsView(AnyRoleMixin, View):
    """Salary & Payroll Analytics Dashboard."""
    template_name = "reports/salary_reports.html"

    def get(self, request):
        if request.user.is_owner and not CompanySettings.get().allow_owner_export:
            raise PermissionDenied("Salary reports are restricted.")
        recent_periods = PayrollPeriod.objects.order_by("-start_date")[:10]
        return render(request, self.template_name, {
            "periods": recent_periods,
            "cycles": PayrollCycle.choices,
            "is_owner": request.user.is_owner,
        })


# ─── CSV Exports ───────────────────────────────────────────────────────────────

class EmployeeListCSVExport(AnyRoleMixin, View):
    """Export complete active and inactive employee roster to CSV."""
    def get(self, request):
        _check_export_permission(request, is_sensitive_salary=False)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID", "Full Name", "Gender", "Date of Birth", "Phone",
            "Email", "Department", "Designation", "Joining Date", "Status",
            "Employment Type", "Shift", "Salary Method", "Base Salary Rate", "Standard Daily Hours"
        ])

        for emp in Employee.objects.select_related("department", "designation", "assigned_shift").order_by("employee_id"):
            base_rate_str = str(emp.base_salary_rate) if not request.user.is_owner else "RESTRICTED"
            writer.writerow([
                SAFE_STR(emp.employee_id),
                SAFE_STR(emp.full_name),
                SAFE_STR(emp.get_gender_display() if emp.gender else ""),
                str(emp.date_of_birth or ""),
                SAFE_STR(emp.phone),
                SAFE_STR(emp.email),
                SAFE_STR(emp.department.name if emp.department else ""),
                SAFE_STR(emp.designation.name if emp.designation else ""),
                str(emp.date_of_joining),
                SAFE_STR(emp.get_employment_status_display()),
                SAFE_STR(emp.get_employment_type_display()),
                SAFE_STR(emp.assigned_shift.name if emp.assigned_shift else "None"),
                SAFE_STR(emp.get_salary_calculation_method_display()),
                base_rate_str,
                str(emp.standard_working_hours),
            ])

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="Employee", target_id="roster_csv",
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"report": "employee_roster_csv"},
        )

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="employee_roster_{timezone.localdate()}.csv"'
        return response


class IndividualAttendanceCSVExport(AnyRoleMixin, View):
    """Export attendance history for a single employee."""
    def get(self, request):
        _check_export_permission(request)
        emp_id = request.GET.get("employee_id")
        if not emp_id:
            raise Http404("Employee ID required.")

        employee = get_object_or_404(Employee, pk=emp_id)
        records = AttendanceRecord.objects.filter(employee=employee).order_by("-work_date")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID", "Name", "Work Date", "Check In", "Check Out",
            "Break (min)", "Net Working Hours", "Regular Hours", "Overtime Hours",
            "Status", "Late?", "Late (min)"
        ])

        for rec in records:
            cin = timezone.localtime(rec.check_in).strftime("%H:%M") if rec.check_in else ""
            cout = timezone.localtime(rec.check_out).strftime("%H:%M") if rec.check_out else ""
            writer.writerow([
                SAFE_STR(employee.employee_id),
                SAFE_STR(employee.full_name),
                str(rec.work_date),
                cin,
                cout,
                rec.break_duration_minutes,
                str(rec.net_working_hours),
                str(rec.regular_hours),
                str(rec.overtime_hours),
                SAFE_STR(rec.get_status_display()),
                "Yes" if rec.is_late else "No",
                rec.late_by_minutes,
            ])

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="AttendanceRecord", target_id=str(employee.pk),
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"report": "individual_attendance_csv", "employee_id": employee.employee_id},
        )

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="attendance_{employee.employee_id}_{timezone.localdate()}.csv"'
        return response


class DailyAttendanceCSVExport(AnyRoleMixin, View):
    """Export attendance summary for a specific date."""
    def get(self, request):
        _check_export_permission(request)
        date_str = request.GET.get("date")
        try:
            work_date = datetime.date.fromisoformat(date_str) if date_str else timezone.localdate()
        except ValueError:
            work_date = timezone.localdate()

        records = AttendanceRecord.objects.filter(work_date=work_date).select_related("employee", "employee__department").order_by("employee__employee_id")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Employee ID", "Name", "Department", "Check In", "Check Out",
            "Break (min)", "Net Hours", "Regular Hours", "OT Hours", "Status", "Late?"
        ])

        for rec in records:
            cin = timezone.localtime(rec.check_in).strftime("%H:%M") if rec.check_in else ""
            cout = timezone.localtime(rec.check_out).strftime("%H:%M") if rec.check_out else ""
            writer.writerow([
                str(rec.work_date),
                SAFE_STR(rec.employee.employee_id),
                SAFE_STR(rec.employee.full_name),
                SAFE_STR(rec.employee.department.name if rec.employee.department else ""),
                cin,
                cout,
                rec.break_duration_minutes,
                str(rec.net_working_hours),
                str(rec.regular_hours),
                str(rec.overtime_hours),
                SAFE_STR(rec.get_status_display()),
                "Yes" if rec.is_late else "No",
            ])

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="AttendanceRecord", target_id=str(work_date),
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"report": "daily_attendance_csv", "date": str(work_date)},
        )

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="daily_attendance_{work_date}.csv"'
        return response


class WeeklyAttendanceCSVExport(AnyRoleMixin, View):
    """Export attendance aggregated for the last 7 days."""
    def get(self, request):
        _check_export_permission(request)
        today = timezone.localdate()
        start_date = today - datetime.timedelta(days=6)

        records = AttendanceRecord.objects.filter(
            work_date__gte=start_date, work_date__lte=today
        ).select_related("employee", "employee__department").order_by("-work_date", "employee__employee_id")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID", "Name", "Department", "Date", "Status", "Net Hours", "OT Hours", "Late?"
        ])

        for r in records:
            writer.writerow([
                SAFE_STR(r.employee.employee_id),
                SAFE_STR(r.employee.full_name),
                SAFE_STR(r.employee.department.name if r.employee.department else ""),
                str(r.work_date),
                SAFE_STR(r.get_status_display()),
                str(r.net_working_hours),
                str(r.overtime_hours),
                "Yes" if r.is_late else "No",
            ])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="weekly_attendance_{start_date}_to_{today}.csv"'
        return response


class MonthlyAttendanceCSVExport(AnyRoleMixin, View):
    """Export attendance for a calendar month."""
    def get(self, request):
        _check_export_permission(request)
        today = timezone.localdate()
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))

        import calendar
        _, last_day = calendar.monthrange(year, month)
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, last_day)

        records = AttendanceRecord.objects.filter(
            work_date__gte=start_date, work_date__lte=end_date
        ).select_related("employee", "employee__department").order_by("work_date", "employee__employee_id")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Employee ID", "Name", "Department", "Status", "Net Hours", "OT Hours", "Late?"
        ])

        for r in records:
            writer.writerow([
                str(r.work_date),
                SAFE_STR(r.employee.employee_id),
                SAFE_STR(r.employee.full_name),
                SAFE_STR(r.employee.department.name if r.employee.department else ""),
                SAFE_STR(r.get_status_display()),
                str(r.net_working_hours),
                str(r.overtime_hours),
                "Yes" if r.is_late else "No",
            ])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="monthly_attendance_{year}_{month:02d}.csv"'
        return response


class WorkingHoursSummaryCSVExport(AnyRoleMixin, View):
    """Summarizes total scheduled, regular, and overtime hours worked per employee."""
    def get(self, request):
        _check_export_permission(request)
        today = timezone.localdate()
        start_date = today.replace(day=1)

        summary = AttendanceRecord.objects.filter(
            work_date__gte=start_date, work_date__lte=today
        ).values("employee__employee_id", "employee__first_name", "employee__last_name").annotate(
            total_net=Sum("net_working_hours"),
            total_regular=Sum("regular_hours"),
            total_ot=Sum("overtime_hours"),
            present_days=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        ).order_by("employee__employee_id")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID", "Name", "Month", "Present Days", "Total Regular Hours", "Total Overtime Hours", "Total Net Working Hours"
        ])

        for s in summary:
            writer.writerow([
                SAFE_STR(s["employee__employee_id"]),
                SAFE_STR(f"{s['employee__first_name']} {s['employee__last_name']}".strip()),
                start_date.strftime("%B %Y"),
                s["present_days"],
                str(s["total_regular"] or "0.00"),
                str(s["total_ot"] or "0.00"),
                str(s["total_net"] or "0.00"),
            ])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="working_hours_summary_{start_date.strftime("%Y_%m")}.csv"'
        return response


class OvertimeSummaryCSVExport(AnyRoleMixin, View):
    """Export detailed overtime hours and rate multiplier breakdown."""
    def get(self, request):
        _check_export_permission(request, is_sensitive_salary=request.user.is_owner)
        today = timezone.localdate()
        start_date = today.replace(day=1)

        records = AttendanceRecord.objects.filter(
            work_date__gte=start_date, work_date__lte=today, overtime_hours__gt=0
        ).select_related("employee").order_by("-work_date")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Employee ID", "Name", "Net Working Hours", "Daily Threshold", "Overtime Hours", "Status"
        ])

        for r in records:
            writer.writerow([
                str(r.work_date),
                SAFE_STR(r.employee.employee_id),
                SAFE_STR(r.employee.full_name),
                str(r.net_working_hours),
                str(r.employee.standard_working_hours),
                str(r.overtime_hours),
                SAFE_STR(r.get_status_display()),
            ])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="overtime_summary_{start_date.strftime("%Y_%m")}.csv"'
        return response


class LeaveSummaryCSVExport(AnyRoleMixin, View):
    """Export leave balances, approved requests, and unpaid leave days."""
    def get(self, request):
        _check_export_permission(request)
        leaves = LeaveRecord.objects.select_related("employee", "approved_by").order_by("-start_date")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Employee ID", "Employee Name", "Leave Type", "Start Date", "End Date",
            "Duration (Days)", "Status", "Reason", "Approved By"
        ])

        for lv in leaves:
            approver_str = lv.approved_by.username if lv.approved_by else "N/A"
            writer.writerow([
                SAFE_STR(lv.employee.employee_id),
                SAFE_STR(lv.employee.full_name),
                SAFE_STR(lv.get_leave_type_display()),
                str(lv.start_date),
                str(lv.end_date),
                lv.duration_days,
                SAFE_STR(lv.get_status_display()),
                SAFE_STR(lv.reason.replace("\n", " ")),
                SAFE_STR(approver_str),
            ])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="leave_summary_{timezone.localdate()}.csv"'
        return response


class PayrollCycleCSVExport(AccountantOrSuperadminMixin, View):
    """Export payroll statements filtered by cycle type (Weekly, Biweekly, Three-Weekly, Monthly)."""
    def get(self, request):
        cycle_type = request.GET.get("cycle", "MONTHLY")
        statements = PayrollStatement.objects.filter(
            payroll_period__cycle_type=cycle_type
        ).select_related("payroll_period", "employee").order_by("-payroll_period__start_date", "employee__employee_id")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Period Cycle", "Start Date", "End Date", "Employee ID", "Employee Name",
            "Salary Method", "Worked Hours", "OT Hours", "Payable Days",
            "Base Pay (₹)", "Overtime Pay (₹)", "Allowances (₹)", "Bonuses (₹)", "Deductions (₹)",
            "Gross Pay (₹)", "Net Pay (₹)", "Status"
        ])

        for st in statements:
            p = st.payroll_period
            writer.writerow([
                SAFE_STR(p.get_cycle_type_display()),
                str(p.start_date),
                str(p.end_date),
                SAFE_STR(st.employee.employee_id),
                SAFE_STR(st.employee.full_name),
                SAFE_STR(st.salary_method),
                str(st.worked_hours),
                str(st.overtime_hours),
                str(st.payable_days),
                str(st.base_pay),
                str(st.overtime_pay),
                str(st.total_allowances),
                str(st.total_bonuses),
                str(st.total_deductions),
                str(st.gross_pay),
                str(st.net_pay),
                SAFE_STR(st.status),
            ])

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="PayrollPeriod", target_id=cycle_type,
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"report": "payroll_cycle_csv", "cycle": cycle_type},
        )

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="payroll_{cycle_type.lower()}_{timezone.localdate()}.csv"'
        return response


# ─── Excel and PDF Exports ─────────────────────────────────────────────────────

class AttendanceExcelExport(AnyRoleMixin, View):
    def get(self, request):
        _check_export_permission(request)
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        emp_id = request.GET.get("employee")
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")

        qs = AttendanceRecord.objects.select_related("employee", "employee__department").order_by("-work_date")
        if emp_id:
            qs = qs.filter(employee_id=emp_id)
        if date_from:
            qs = qs.filter(work_date__gte=date_from)
        if date_to:
            qs = qs.filter(work_date__lte=date_to)

        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        header_fill = PatternFill("solid", fgColor="1E3A5F")
        header_font = Font(color="FFFFFF", bold=True)

        headers = [
            "Employee ID", "Name", "Department", "Date",
            "Check In", "Check Out", "Break (min)", "Net Hours",
            "Regular Hours", "Overtime Hours", "Status", "Late?", "Late By (min)"
        ]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for row_idx, rec in enumerate(qs, 2):
            ws.cell(row=row_idx, column=1, value=SAFE_STR(rec.employee.employee_id))
            ws.cell(row=row_idx, column=2, value=SAFE_STR(rec.employee.full_name))
            ws.cell(row=row_idx, column=3, value=SAFE_STR(rec.employee.department.name if rec.employee.department else ""))
            ws.cell(row=row_idx, column=4, value=str(rec.work_date))
            ws.cell(row=row_idx, column=5, value=str(timezone.localtime(rec.check_in).strftime("%H:%M") if rec.check_in else ""))
            ws.cell(row=row_idx, column=6, value=str(timezone.localtime(rec.check_out).strftime("%H:%M") if rec.check_out else ""))
            ws.cell(row=row_idx, column=7, value=rec.break_duration_minutes)
            ws.cell(row=row_idx, column=8, value=float(rec.net_working_hours or 0))
            ws.cell(row=row_idx, column=9, value=float(rec.regular_hours or 0))
            ws.cell(row=row_idx, column=10, value=float(rec.overtime_hours or 0))
            ws.cell(row=row_idx, column=11, value=SAFE_STR(rec.get_status_display()))
            ws.cell(row=row_idx, column=12, value="Yes" if rec.is_late else "No")
            ws.cell(row=row_idx, column=13, value=rec.late_by_minutes)

        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 16

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="AttendanceRecord", target_id="batch",
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "excel", "report": "attendance"},
        )

        filename = f"attendance_report_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
        response = HttpResponse(
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PayrollExcelExport(AccountantOrSuperadminMixin, View):
    def get(self, request, period_pk):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        period = get_object_or_404(PayrollPeriod, pk=period_pk)
        statements = PayrollStatement.objects.filter(payroll_period=period).select_related("employee")

        wb = Workbook()
        ws = wb.active
        ws.title = f"Payroll {period.start_date}"

        header_fill = PatternFill("solid", fgColor="1E3A5F")
        header_font = Font(color="FFFFFF", bold=True)

        headers = [
            "Employee ID", "Name", "Salary Method", "Period Start", "Period End",
            "Worked Hours", "Regular Hours", "OT Hours", "Payable Days",
            "Base Pay (₹)", "OT Pay (₹)", "Allowances (₹)", "Bonuses (₹)", "Deductions (₹)",
            "Gross Pay (₹)", "Net Pay (₹)", "Status",
        ]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font

        for row_idx, stmt in enumerate(statements, 2):
            row = [
                SAFE_STR(stmt.employee.employee_id),
                SAFE_STR(stmt.employee.full_name),
                SAFE_STR(stmt.salary_method),
                str(period.start_date),
                str(period.end_date),
                float(stmt.worked_hours or 0),
                float(stmt.regular_hours or 0),
                float(stmt.overtime_hours or 0),
                float(stmt.payable_days or 0),
                float(stmt.base_pay or 0),
                float(stmt.overtime_pay or 0),
                float(stmt.total_allowances or 0),
                float(stmt.total_bonuses or 0),
                float(stmt.total_deductions or 0),
                float(stmt.gross_pay or 0),
                float(stmt.net_pay or 0),
                SAFE_STR(stmt.status),
            ]
            for col, val in enumerate(row, 1):
                ws.cell(row=row_idx, column=col, value=val)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="PayrollPeriod", target_id=str(period.pk),
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "excel", "report": "payroll"},
        )

        filename = f"payroll_{period.start_date}_{period.end_date}.xlsx"
        response = HttpResponse(
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PayrollPDFExport(AccountantOrSuperadminMixin, View):
    def get(self, request, period_pk):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        period = get_object_or_404(PayrollPeriod, pk=period_pk)
        statements = PayrollStatement.objects.filter(payroll_period=period).select_related("employee")
        settings_obj = CompanySettings.get()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=20, rightMargin=20)
        styles = getSampleStyleSheet()

        elements = []
        title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#1E3A5F"))
        elements.append(Paragraph(f"{settings_obj.company_name} — Payroll Report", title_style))
        elements.append(Paragraph(f"Period: {period.start_date} to {period.end_date} | Cycle: {period.get_cycle_type_display()}", styles["Normal"]))
        elements.append(Spacer(1, 12))

        table_data = [["Emp ID", "Name", "Method", "Worked Hrs", "OT Hrs", "Base Pay", "OT Pay", "Allowances", "Bonuses", "Deductions", "Gross", "Net", "Status"]]
        for stmt in statements:
            table_data.append([
                SAFE_STR(stmt.employee.employee_id),
                SAFE_STR(stmt.employee.full_name),
                stmt.salary_method,
                f"{stmt.worked_hours:.2f}",
                f"{stmt.overtime_hours:.2f}",
                f"{settings_obj.currency_symbol}{stmt.base_pay:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.overtime_pay:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.total_allowances:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.total_bonuses:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.total_deductions:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.gross_pay:,.2f}",
                f"{settings_obj.currency_symbol}{stmt.net_pay:,.2f}",
                stmt.status,
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4F8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(table)
        doc.build(elements)

        buffer.seek(0)
        audit_log(
            actor=request.user, action="REPORT_EXPORT",
            target_model="PayrollPeriod", target_id=str(period.pk),
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "pdf", "report": "payroll"},
        )

        filename = f"payroll_{period.start_date}_{period.end_date}.pdf"
        response = HttpResponse(buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

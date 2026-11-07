"""
Thamarayyath Employee Portal — Reports URL Configuration.
"""

from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    # Hubs
    path("", views.ReportsHubView.as_view(), name="hub"),
    path("attendance/", views.AttendanceReportsView.as_view(), name="attendance_reports"),
    path("salary/", views.SalaryReportsView.as_view(), name="salary_reports"),

    # CSV Exports
    path("employees/csv/", views.EmployeeListCSVExport.as_view(), name="employees_csv"),
    path("attendance/individual/csv/", views.IndividualAttendanceCSVExport.as_view(), name="individual_attendance_csv"),
    path("attendance/daily/csv/", views.DailyAttendanceCSVExport.as_view(), name="daily_attendance_csv"),
    path("attendance/weekly/csv/", views.WeeklyAttendanceCSVExport.as_view(), name="weekly_attendance_csv"),
    path("attendance/monthly/csv/", views.MonthlyAttendanceCSVExport.as_view(), name="monthly_attendance_csv"),
    path("working-hours/csv/", views.WorkingHoursSummaryCSVExport.as_view(), name="working_hours_csv"),
    path("overtime/csv/", views.OvertimeSummaryCSVExport.as_view(), name="overtime_csv"),
    path("leave/csv/", views.LeaveSummaryCSVExport.as_view(), name="leave_csv"),
    path("payroll/cycle/csv/", views.PayrollCycleCSVExport.as_view(), name="payroll_cycle_csv"),

    # Excel and PDF Exports
    path("attendance/excel/", views.AttendanceExcelExport.as_view(), name="attendance_excel"),
    path("payroll/<int:period_pk>/excel/", views.PayrollExcelExport.as_view(), name="payroll_excel"),
    path("payroll/<int:period_pk>/pdf/", views.PayrollPDFExport.as_view(), name="payroll_pdf"),
]

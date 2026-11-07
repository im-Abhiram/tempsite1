"""
Thamarayyath Employee Portal — Core URL Configuration.
"""

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("backup/", views.BackupDashboardView.as_view(), name="backup_dashboard"),
    path("backup/database/", views.DatabaseBackupDownloadView.as_view(), name="download_db_backup"),
    path("backup/employees/csv/", views.EmployeesCSVBackupView.as_view(), name="download_employees_csv"),
    path("backup/attendance/csv/", views.AttendanceCSVBackupView.as_view(), name="download_attendance_csv"),
    path("backup/payroll/csv/", views.PayrollCSVBackupView.as_view(), name="download_payroll_csv"),
]


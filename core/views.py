"""
Thamarayyath Employee Portal — Core Views.
Superadmin-only database and CSV backup downloads, storage monitoring, and restore instructions.
"""

import logging
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View

from accounts.permissions import SuperadminRequiredMixin
from audit.services import audit_log
from .services import (
    get_sqlite_backup_bytes, get_storage_usage,
    generate_employees_csv_backup, generate_attendance_csv_backup, generate_payroll_csv_backup
)

logger = logging.getLogger("portal")


class BackupDashboardView(SuperadminRequiredMixin, View):
    """
    Superadmin Backup & Restore management screen.
    Displays live disk usage, one-click downloads, and step-by-step restoration instructions.
    """
    template_name = "core/backup_dashboard.html"

    def get(self, request):
        storage_info = get_storage_usage()
        return render(request, self.template_name, {
            "storage": storage_info,
            "now": timezone.now(),
        })


class DatabaseBackupDownloadView(SuperadminRequiredMixin, View):
    """
    Downloads an atomic, live SQLite binary snapshot using sqlite3 online backup API.
    Guarantees no database corruption or table-locking issues.
    """
    def get(self, request):
        try:
            backup_bytes = get_sqlite_backup_bytes()
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            filename = f"thamarayyath_portal_backup_{timestamp}.sqlite3"

            audit_log(
                actor=request.user,
                action="SETTINGS_UPDATE",
                target_model="DatabaseBackup",
                target_id=filename,
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"type": "sqlite3_binary_snapshot", "size_bytes": len(backup_bytes)},
            )

            response = HttpResponse(backup_bytes, content_type="application/x-sqlite3")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception as exc:
            logger.error("Database backup generation failed: %s", exc)
            messages.error(request, f"Failed to generate database backup: {exc}")
            return redirect("core:backup_dashboard")


class EmployeesCSVBackupView(SuperadminRequiredMixin, View):
    """Downloads full employee master database in CSV format."""
    def get(self, request):
        csv_data = generate_employees_csv_backup()
        timestamp = timezone.now().strftime("%Y%m%d_%H%M")
        filename = f"employees_master_backup_{timestamp}.csv"

        audit_log(
            actor=request.user,
            action="REPORT_EXPORT",
            target_model="EmployeeBackup",
            target_id=filename,
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "csv", "type": "master_employees"},
        )

        response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class AttendanceCSVBackupView(SuperadminRequiredMixin, View):
    """Downloads complete attendance ledger in CSV format."""
    def get(self, request):
        csv_data = generate_attendance_csv_backup()
        timestamp = timezone.now().strftime("%Y%m%d_%H%M")
        filename = f"attendance_ledger_backup_{timestamp}.csv"

        audit_log(
            actor=request.user,
            action="REPORT_EXPORT",
            target_model="AttendanceBackup",
            target_id=filename,
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "csv", "type": "master_attendance"},
        )

        response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PayrollCSVBackupView(SuperadminRequiredMixin, View):
    """Downloads complete payroll history in CSV format."""
    def get(self, request):
        csv_data = generate_payroll_csv_backup()
        timestamp = timezone.now().strftime("%Y%m%d_%H%M")
        filename = f"payroll_history_backup_{timestamp}.csv"

        audit_log(
            actor=request.user,
            action="REPORT_EXPORT",
            target_model="PayrollBackup",
            target_id=filename,
            ip_address=request.META.get("REMOTE_ADDR"),
            extra={"format": "csv", "type": "master_payroll"},
        )

        response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


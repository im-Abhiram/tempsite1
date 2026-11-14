"""
Thamarayyath Employee Portal — Audit Log Model.

Append-only record of all security events and business-critical operations.
Application-layer users cannot edit or delete this table.
DB-level enforcement: the application DB user should not have DELETE/UPDATE on this table in production.
"""

import json
from django.db import models
from django.conf import settings
from django.utils import timezone


class AuditLog(models.Model):
    """
    Immutable event log. Each row represents one security or business event.
    Never update or delete rows from application code.
    """

    # Event categories
    class Action(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login Success"
        LOGIN_FAIL = "LOGIN_FAIL", "Login Failure"
        LOGOUT = "LOGOUT", "Logout"
        ACCOUNT_CREATE = "ACCOUNT_CREATE", "Account Created"
        ACCOUNT_UPDATE = "ACCOUNT_UPDATE", "Account Updated"
        ACCOUNT_SUSPEND = "ACCOUNT_SUSPEND", "Account Suspended"
        ACCOUNT_ACTIVATE = "ACCOUNT_ACTIVATE", "Account Activated"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Password Changed"
        PASSWORD_RESET = "PASSWORD_RESET", "Password Reset (by Admin)"
        ROLE_CHANGE = "ROLE_CHANGE", "Role Changed"
        SETTINGS_UPDATE = "SETTINGS_UPDATE", "Settings Updated"
        EMPLOYEE_CREATE = "EMPLOYEE_CREATE", "Employee Created"
        EMPLOYEE_UPDATE = "EMPLOYEE_UPDATE", "Employee Updated"
        EMPLOYEE_DEACTIVATE = "EMPLOYEE_DEACTIVATE", "Employee Deactivated"
        EMPLOYEE_DELETE = "EMPLOYEE_DELETE", "Employee Deleted"
        DEPARTMENT_CREATE = "DEPARTMENT_CREATE", "Department Created"
        DEPARTMENT_UPDATE = "DEPARTMENT_UPDATE", "Department Updated"
        DEPARTMENT_DELETE = "DEPARTMENT_DELETE", "Department Deleted"
        SHIFT_CREATE = "SHIFT_CREATE", "Shift Created"
        SHIFT_UPDATE = "SHIFT_UPDATE", "Shift Updated"
        SHIFT_DELETE = "SHIFT_DELETE", "Shift Deleted"
        HOLIDAY_CREATE = "HOLIDAY_CREATE", "Holiday Created"
        HOLIDAY_DELETE = "HOLIDAY_DELETE", "Holiday Deleted"
        SALARY_UPDATE = "SALARY_UPDATE", "Salary Rate Updated"
        DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD", "Document Uploaded"
        DOCUMENT_DOWNLOAD = "DOCUMENT_DOWNLOAD", "Document Downloaded"
        ATTENDANCE_MARK = "ATTENDANCE_MARK", "Attendance Marked"
        ATTENDANCE_CORRECT = "ATTENDANCE_CORRECT", "Attendance Corrected"
        PAYROLL_GENERATE = "PAYROLL_GENERATE", "Payroll Generated"
        PAYROLL_REVIEW = "PAYROLL_REVIEW", "Payroll Reviewed"
        PAYROLL_FINALIZE = "PAYROLL_FINALIZE", "Payroll Finalized"
        PAYROLL_REVERSE = "PAYROLL_REVERSE", "Payroll Reversed"
        REPORT_EXPORT = "REPORT_EXPORT", "Report Exported"
        IMPORT_EMPLOYEE = "IMPORT_EMPLOYEE", "Employee Data Imported"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        db_index=True,
    )
    actor_username = models.CharField(
        max_length=150, blank=True,
        help_text="Snapshot of username at time of event (preserved if account is deleted).",
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=[("SUCCESS", "Success"), ("FAILURE", "Failure")],
        default="SUCCESS",
    )
    extra = models.JSONField(
        default=dict,
        help_text="Additional context. Never log passwords, tokens, or full PII.",
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["actor", "timestamp"]),
            models.Index(fields=["target_model", "target_id"]),
        ]
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log"

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.actor_username} — {self.action}"

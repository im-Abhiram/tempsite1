"""
Thamarayyath Employee Portal — Core Services.
Provides consistent SQLite backups, storage usage tracking, and safe CSV data dumps.
"""

import csv
import io
import os
import shutil
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.db import connection
from django.utils import timezone

SAFE_STR = lambda v: ("'" + str(v)) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else str(v)


def get_sqlite_backup_bytes() -> bytes:
    """
    Creates a consistent, atomic binary snapshot of the SQLite database using SQLite's
    native online backup API. This eliminates race conditions or database corruption
    that occurs when simply copying an active db.sqlite3 file while it is being written.
    """
    db_path = settings.DATABASES["default"]["NAME"]
    
    # If using Django connection directly:
    src_conn = sqlite3.connect(db_path)
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tf:
        temp_dest_path = tf.name

    try:
        dest_conn = sqlite3.connect(temp_dest_path)
        src_conn.backup(dest_conn)
        dest_conn.close()
        src_conn.close()

        with open(temp_dest_path, "rb") as f:
            backup_data = f.read()
    finally:
        if os.path.exists(temp_dest_path):
            os.remove(temp_dest_path)

    return backup_data


def get_storage_usage() -> dict:
    """
    Calculates disk space used by SQLite database, uploaded media, and log files.
    Helpful for PythonAnywhere free accounts (512 MB storage quota).
    """
    base_dir = Path(settings.BASE_DIR)
    db_path = Path(settings.DATABASES["default"]["NAME"])
    media_dir = Path(settings.MEDIA_ROOT)
    logs_dir = base_dir / "logs"

    db_size = db_path.stat().st_size if db_path.exists() else 0

    def dir_size(p: Path) -> int:
        if not p.exists():
            return 0
        return sum(f.stat().st_size for f in p.glob("**/*") if f.is_file())

    media_size = dir_size(media_dir)
    logs_size = dir_size(logs_dir)
    total_portal_size = db_size + media_size + logs_size

    def format_bytes(b: int) -> str:
        if b < 1024:
            return f"{b} B"
        elif b < 1024 ** 2:
            return f"{b / 1024:.1f} KB"
        elif b < 1024 ** 3:
            return f"{b / (1024 ** 2):.2f} MB"
        return f"{b / (1024 ** 3):.2f} GB"

    return {
        "db_size_bytes": db_size,
        "db_size_display": format_bytes(db_size),
        "media_size_bytes": media_size,
        "media_size_display": format_bytes(media_size),
        "logs_size_bytes": logs_size,
        "logs_size_display": format_bytes(logs_size),
        "total_size_bytes": total_portal_size,
        "total_size_display": format_bytes(total_portal_size),
    }


def generate_employees_csv_backup() -> str:
    """Export complete employee records to a clean, sanitized CSV string."""
    from employees.models import Employee

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee ID", "First Name", "Last Name", "Gender", "Date of Birth",
        "Phone", "Email", "Department", "Designation", "Joining Date",
        "Status", "Employment Type", "Salary Method", "Base Salary Rate",
        "Standard Hours", "Overtime Eligible", "Custom OT Rate",
        "Bank Name", "Account Number", "IFSC Code", "Branch", "Address", "Notes"
    ])

    for emp in Employee.objects.select_related("department", "designation").order_by("employee_id"):
        writer.writerow([
            SAFE_STR(emp.employee_id),
            SAFE_STR(emp.first_name),
            SAFE_STR(emp.last_name),
            SAFE_STR(emp.get_gender_display() if emp.gender else ""),
            str(emp.date_of_birth or ""),
            SAFE_STR(emp.phone),
            SAFE_STR(emp.email),
            SAFE_STR(emp.department.name if emp.department else ""),
            SAFE_STR(emp.designation.name if emp.designation else ""),
            str(emp.date_of_joining),
            SAFE_STR(emp.get_employment_status_display()),
            SAFE_STR(emp.get_employment_type_display()),
            SAFE_STR(emp.get_salary_calculation_method_display()),
            str(emp.base_salary_rate),
            str(emp.standard_working_hours),
            "Yes" if emp.overtime_eligible else "No",
            str(emp.custom_overtime_rate or ""),
            SAFE_STR(emp.bank_name),
            SAFE_STR(emp.bank_account_number),
            SAFE_STR(emp.bank_ifsc_code),
            SAFE_STR(emp.bank_branch_name),
            SAFE_STR(emp.residential_address.replace("\n", " ")),
            SAFE_STR(emp.notes.replace("\n", " ")),
        ])

    return output.getvalue()


def generate_attendance_csv_backup() -> str:
    """Export complete attendance records to a clean, sanitized CSV string."""
    from attendance.models import AttendanceRecord

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee ID", "Employee Name", "Work Date", "Check In", "Check Out",
        "Break Duration (mins)", "Net Working Hours", "Regular Hours",
        "Overtime Hours", "Status", "Entry Method", "Late?", "Late Minutes",
        "Locked by Payroll?", "Correction Reason"
    ])

    for rec in AttendanceRecord.objects.select_related("employee").order_by("-work_date", "employee__employee_id"):
        check_in_str = timezone.localtime(rec.check_in).strftime("%Y-%m-%d %H:%M:%S") if rec.check_in else ""
        check_out_str = timezone.localtime(rec.check_out).strftime("%Y-%m-%d %H:%M:%S") if rec.check_out else ""
        writer.writerow([
            SAFE_STR(rec.employee.employee_id),
            SAFE_STR(rec.employee.full_name),
            str(rec.work_date),
            check_in_str,
            check_out_str,
            rec.break_duration_minutes,
            str(rec.net_working_hours),
            str(rec.regular_hours),
            str(rec.overtime_hours),
            SAFE_STR(rec.get_status_display()),
            SAFE_STR(rec.get_entry_method_display()),
            "Yes" if rec.is_late else "No",
            rec.late_by_minutes,
            "Yes" if rec.is_locked_by_payroll else "No",
            SAFE_STR(rec.correction_reason.replace("\n", " ")),
        ])

    return output.getvalue()


def generate_payroll_csv_backup() -> str:
    """Export complete finalized and draft payroll statements to CSV."""
    from payroll.models import PayrollStatement

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Period Cycle", "Period Start", "Period End", "Employee ID", "Employee Name",
        "Salary Method", "Base Rate", "Worked Hours", "Regular Hours", "OT Hours",
        "Payable Days", "Base Pay", "Overtime Pay", "Allowances", "Bonuses",
        "Deductions", "Gross Pay", "Net Pay", "Status", "Finalized At"
    ])

    for stmt in PayrollStatement.objects.select_related("payroll_period", "employee").order_by("-payroll_period__start_date", "employee__employee_id"):
        p = stmt.payroll_period
        finalized_str = timezone.localtime(stmt.finalized_at).strftime("%Y-%m-%d %H:%M:%S") if stmt.finalized_at else ""
        writer.writerow([
            SAFE_STR(p.get_cycle_type_display()),
            str(p.start_date),
            str(p.end_date),
            SAFE_STR(stmt.employee.employee_id),
            SAFE_STR(stmt.employee.full_name),
            SAFE_STR(stmt.salary_method),
            str(stmt.base_rate),
            str(stmt.worked_hours),
            str(stmt.regular_hours),
            str(stmt.overtime_hours),
            str(stmt.payable_days),
            str(stmt.base_pay),
            str(stmt.overtime_pay),
            str(stmt.total_allowances),
            str(stmt.total_bonuses),
            str(stmt.total_deductions),
            str(stmt.gross_pay),
            str(stmt.net_pay),
            SAFE_STR(stmt.status),
            finalized_str,
        ])

    return output.getvalue()


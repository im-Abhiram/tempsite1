"""
Thamarayyath Employee Portal — Employee Views.

All views enforce server-side permissions.
Private documents are served through a controlled view, never via predictable URLs.
"""

import os
import logging
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView

from accounts.models import CompanySettings
from accounts.permissions import (
    AnyRoleMixin, AccountantOrSuperadminMixin, NotOwnerMixin,
    AccountantRequiredMixin, assert_can_view_employee, assert_can_edit_employee,
)
from audit.services import audit_log
from .forms import (
    EmployeeForm, DepartmentForm, DesignationForm, ShiftForm,
    SalaryRateUpdateForm, DocumentUploadForm,
)
from .models import (
    Employee, Department, Designation, Shift, SalaryRateHistory,
    EmployeeDocument, EmploymentStatus,
)

logger = logging.getLogger("portal")
User = get_user_model()


# ─── Dashboard Redirect ────────────────────────────────────────────────────────

class DashboardView(AnyRoleMixin, View):
    def get(self, request):
        from dashboard.views import DashboardRouterView
        return DashboardRouterView().get(request)


def _superadmin_context(request):
    from accounts.models import CustomUser, Role
    from audit.models import AuditLog
    from attendance.models import AttendanceRecord, AttendanceStatus
    from django.utils.timezone import now
    today = now().date()
    office_admin_count = CustomUser.objects.filter(role__in=[Role.OFFICE_ADMIN, "ACCOUNTANT"]).count()
    return {
        "total_employees": Employee.objects.count(),
        "active_employees": Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).count(),
        "inactive_employees": Employee.objects.exclude(employment_status=EmploymentStatus.ACTIVE).count(),
        "accountant_count": office_admin_count,
        "office_admin_count": office_admin_count,
        "owner_count": CustomUser.objects.filter(role=Role.OWNER).count(),
        "recent_events": AuditLog.objects.select_related("actor").order_by("-timestamp")[:10],
        "failed_logins": AuditLog.objects.filter(action="LOGIN_FAIL").count(),
        "today_present": AttendanceRecord.objects.filter(work_date=today, status=AttendanceStatus.PRESENT).count(),
    }


def _office_admin_context(request):
    from attendance.models import AttendanceRecord, AttendanceStatus
    from django.utils.timezone import now
    today = now().date()
    active_emp = Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE)
    active_count = active_emp.count()
    present_today = AttendanceRecord.objects.filter(work_date=today, status=AttendanceStatus.PRESENT).count()
    incomplete = AttendanceRecord.objects.filter(work_date=today, status=AttendanceStatus.INCOMPLETE).count()
    return {
        "active_employees": active_count,
        "present_today": present_today,
        "absent_today": active_count - present_today,
        "incomplete_attendance": incomplete,
    }


_accountant_context = _office_admin_context


def _owner_context(request):
    from attendance.models import AttendanceRecord, AttendanceStatus
    from django.utils.timezone import now
    today = now().date()
    return {
        "total_employees": Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).count(),
        "present_today": AttendanceRecord.objects.filter(work_date=today, status=AttendanceStatus.PRESENT).count(),
    }


# ─── Employee CRUD ─────────────────────────────────────────────────────────────

class EmployeeListView(AnyRoleMixin, ListView):
    model = Employee
    template_name = "employees/employee_list.html"
    context_object_name = "employees"
    paginate_by = 25

    def get_queryset(self):
        qs = Employee.objects.select_related("department", "designation", "assigned_shift").order_by("employee_id")
        q = self.request.GET.get("q", "").strip()
        dept = self.request.GET.get("dept", "")
        status = self.request.GET.get("status", "")
        emp_type = self.request.GET.get("type", "")

        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(employee_id__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        if dept:
            qs = qs.filter(department_id=dept)
        if status:
            qs = qs.filter(employment_status=status)
        if emp_type:
            qs = qs.filter(employment_type=emp_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["departments"] = Department.objects.filter(is_active=True)
        ctx["statuses"] = EmploymentStatus.choices
        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_dept"] = self.request.GET.get("dept", "")
        ctx["selected_status"] = self.request.GET.get("status", "")
        return ctx


class EmployeeDetailView(AnyRoleMixin, View):
    template_name = "employees/employee_detail.html"

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        assert_can_view_employee(request.user, employee)
        salary_history = employee.salary_history.select_related("changed_by").order_by("-effective_date")[:10]
        documents = employee.documents.select_related("uploaded_by").all() if not request.user.is_owner else []
        return render(request, self.template_name, {
            "employee": employee,
            "salary_history": salary_history,
            "documents": documents,
            "can_edit": not request.user.is_owner,
            "show_bank_details": not request.user.is_owner,
        })


class EmployeeCreateView(AccountantOrSuperadminMixin, View):
    template_name = "employees/employee_form.html"

    def get(self, request):
        return render(request, self.template_name, {
            "form": EmployeeForm(),
            "action": "Create Employee",
            "existing_designations": Designation.objects.select_related("department").all(),
        })

    def post(self, request):
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                employee = form.save(commit=False)
                employee.created_by = request.user
                employee.save()
                # Create initial salary rate history entry
                SalaryRateHistory.objects.create(
                    employee=employee,
                    effective_date=employee.date_of_joining,
                    salary_calculation_method=employee.salary_calculation_method,
                    base_rate=employee.base_salary_rate,
                    overtime_rate=employee.custom_overtime_rate,
                    changed_by=request.user,
                    reason="Initial employment record.",
                )
                audit_log(
                    actor=request.user, action="EMPLOYEE_CREATE",
                    target_model="Employee", target_id=str(employee.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": employee.employee_id, "name": employee.full_name},
                )
            messages.success(request, f"Employee '{employee.full_name}' ({employee.employee_id}) created.")
            return redirect("employees:employee_detail", pk=employee.pk)
        return render(request, self.template_name, {
            "form": form,
            "action": "Create Employee",
            "existing_designations": Designation.objects.select_related("department").all(),
        })


class EmployeeUpdateView(AccountantOrSuperadminMixin, View):
    template_name = "employees/employee_form.html"

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        assert_can_edit_employee(request.user, employee)
        return render(request, self.template_name, {
            "form": EmployeeForm(instance=employee),
            "action": "Edit Employee",
            "employee": employee,
            "existing_designations": Designation.objects.select_related("department").all(),
        })

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        assert_can_edit_employee(request.user, employee)
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            with transaction.atomic():
                employee = form.save()
                audit_log(
                    actor=request.user, action="EMPLOYEE_UPDATE",
                    target_model="Employee", target_id=str(employee.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": employee.employee_id},
                )
            messages.success(request, f"Employee '{employee.full_name}' updated.")
            return redirect("employees:employee_detail", pk=employee.pk)
        return render(request, self.template_name, {
            "form": form,
            "action": "Edit Employee",
            "employee": employee,
            "existing_designations": Designation.objects.select_related("department").all(),
        })


class EmployeeDeleteView(AccountantOrSuperadminMixin, View):
    template_name = "employees/employee_confirm_delete.html"

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        assert_can_edit_employee(request.user, employee)
        has_finalized_payroll = employee.payroll_statements.filter(status="FINALIZED").exists()
        statement_count = employee.payroll_statements.count()
        attendance_count = employee.attendance_records.count()
        return render(request, self.template_name, {
            "employee": employee,
            "has_finalized_payroll": has_finalized_payroll,
            "statement_count": statement_count,
            "attendance_count": attendance_count,
        })

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        assert_can_edit_employee(request.user, employee)
        emp_name = employee.full_name
        emp_id = employee.employee_id

        try:
            with transaction.atomic():
                employee.delete()
                audit_log(
                    actor=request.user, action="EMPLOYEE_DELETE",
                    target_model="Employee", target_id=str(pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": emp_id, "name": emp_name},
                )
            messages.success(request, f"Employee '{emp_name}' ({emp_id}) deleted successfully.")
            return redirect("employees:employee_list")
        except models.ProtectedError:
            with transaction.atomic():
                employee.employment_status = EmploymentStatus.TERMINATED
                employee.save(update_fields=["employment_status", "updated_at"])
                audit_log(
                    actor=request.user, action="EMPLOYEE_DEACTIVATE",
                    target_model="Employee", target_id=str(pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": emp_id, "name": emp_name, "reason": "Protected by finalized payroll statements"},
                )
            messages.warning(
                request,
                f"Employee '{emp_name}' ({emp_id}) has finalized payroll statements and cannot be removed for audit compliance. Their status has been set to Terminated."
            )
            return redirect("employees:employee_list")



# ─── Salary Rate Update ─────────────────────────────────────────────────────────

class SalaryUpdateView(AccountantOrSuperadminMixin, View):
    template_name = "employees/salary_update.html"

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        return render(request, self.template_name, {
            "employee": employee,
            "form": SalaryRateUpdateForm(),
            "salary_history": employee.salary_history.select_related("changed_by").all()[:10],
        })

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        form = SalaryRateUpdateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Close previous rate's end_date
                SalaryRateHistory.objects.filter(
                    employee=employee, end_date__isnull=True
                ).update(end_date=form.cleaned_data["effective_date"])

                new_entry = SalaryRateHistory.objects.create(
                    employee=employee,
                    effective_date=form.cleaned_data["effective_date"],
                    salary_calculation_method=form.cleaned_data["salary_calculation_method"],
                    base_rate=form.cleaned_data["base_rate"],
                    overtime_rate=form.cleaned_data.get("overtime_rate"),
                    changed_by=request.user,
                    reason=form.cleaned_data["reason"],
                )
                # Update employee's current rate for quick reference
                employee.salary_calculation_method = form.cleaned_data["salary_calculation_method"]
                employee.base_salary_rate = form.cleaned_data["base_rate"]
                employee.custom_overtime_rate = form.cleaned_data.get("overtime_rate")
                employee.save(update_fields=[
                    "salary_calculation_method", "base_salary_rate", "custom_overtime_rate"
                ])

                audit_log(
                    actor=request.user, action="SALARY_UPDATE",
                    target_model="Employee", target_id=str(employee.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "employee_id": employee.employee_id,
                        "new_base_rate": str(form.cleaned_data["base_rate"]),
                        "method": form.cleaned_data["salary_calculation_method"],
                        "effective_date": str(form.cleaned_data["effective_date"]),
                        "reason": form.cleaned_data["reason"],
                    },
                )
            messages.success(request, "Salary rate updated and history entry created.")
            return redirect("employees:employee_detail", pk=employee.pk)
        return render(request, self.template_name, {
            "employee": employee,
            "form": form,
            "salary_history": employee.salary_history.select_related("changed_by").all()[:10],
        })


# ─── Document Vault ─────────────────────────────────────────────────────────────

class DocumentUploadView(AccountantOrSuperadminMixin, View):
    template_name = "employees/document_upload.html"

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        return render(request, self.template_name, {"employee": employee, "form": DocumentUploadForm()})

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            # Compress uploaded document (scanned photos, ID cards, certificates)
            from core.compression import compress_uploaded_document
            uploaded_file = compress_uploaded_document(uploaded_file, max_dimension=1600, quality=75)

            detected_mime = getattr(uploaded_file, "_detected_mime", "")
            if not detected_mime:
                import mimetypes
                detected_mime = mimetypes.guess_type(uploaded_file.name)[0] or "application/octet-stream"

            with transaction.atomic():
                doc = form.save(commit=False)
                doc.employee = employee
                doc.file = uploaded_file
                doc.original_filename = getattr(uploaded_file, "name", "document")
                doc.file_size = getattr(uploaded_file, "size", 0)
                doc.detected_content_type = detected_mime
                doc.uploaded_by = request.user
                # Redirect file storage to private vault
                doc.file.field.upload_to = lambda inst, fn: _vault_path(fn)
                doc.save()
                audit_log(
                    actor=request.user, action="DOCUMENT_UPLOAD",
                    target_model="EmployeeDocument", target_id=str(doc.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={"employee_id": employee.employee_id, "doc_title": doc.title, "file_size": doc.file_size},
                )
            messages.success(request, f"Document '{doc.title}' uploaded successfully ({doc.file_size_display}).")
            return redirect("employees:employee_detail", pk=employee.pk)
        return render(request, self.template_name, {"employee": employee, "form": form})


def _vault_path(filename):
    import uuid
    ext = os.path.splitext(filename)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


class DocumentServeView(AccountantOrSuperadminMixin, View):
    """
    Serve private vault documents through a controlled access check.
    Documents are NEVER served through predictable public URLs.
    """

    def get(self, request, doc_pk):
        doc = get_object_or_404(EmployeeDocument, pk=doc_pk)
        # Owners are explicitly denied document downloads
        if request.user.is_owner:
            raise PermissionDenied("Document access is not permitted for this role.")

        audit_log(
            actor=request.user, action="DOCUMENT_DOWNLOAD",
            target_model="EmployeeDocument", target_id=str(doc.pk),
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        from django.conf import settings
        vault_root = settings.PRIVATE_VAULT_ROOT
        file_path = vault_root / doc.file.name

        if not file_path.exists():
            raise Http404("Document file not found.")

        # Path traversal check
        try:
            file_path.resolve().relative_to(vault_root.resolve())
        except ValueError:
            raise Http404("Invalid file path.")

        response = FileResponse(
            open(file_path, "rb"),
            content_type=doc.detected_content_type or "application/octet-stream",
            as_attachment=True,
            filename=doc.original_filename,
        )
        return response


# ─── Lookup Management (Superadmin / Accountant) ────────────────────────────────

class DepartmentListView(AccountantOrSuperadminMixin, ListView):
    model = Department
    template_name = "employees/department_list.html"
    context_object_name = "departments"


class DepartmentCreateView(AccountantOrSuperadminMixin, View):
    def get(self, request):
        return render(request, "employees/lookup_form.html", {"form": DepartmentForm(), "title": "Add Department"})

    def post(self, request):
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Department created.")
            return redirect("employees:department_list")
        return render(request, "employees/lookup_form.html", {"form": form, "title": "Add Department"})


class DepartmentDeleteView(AccountantOrSuperadminMixin, View):
    template_name = "employees/department_confirm_delete.html"

    def get(self, request, pk):
        department = get_object_or_404(Department, pk=pk)
        return render(request, self.template_name, {
            "department": department,
            "employee_count": department.employees.count(),
        })

    def post(self, request, pk):
        department = get_object_or_404(Department, pk=pk)
        dept_name = department.name
        emp_count = department.employees.count()
        if emp_count > 0:
            messages.error(
                request,
                f"Cannot delete department '{dept_name}' because {emp_count} employee(s) are assigned to it. Please reassign them before deleting."
            )
            return redirect("employees:department_list")

        if department.designations.exists():
            messages.error(
                request,
                f"Cannot delete department '{dept_name}' because designations are associated with it. Please remove or reassign designations first."
            )
            return redirect("employees:department_list")

        with transaction.atomic():
            department.delete()
            audit_log(
                actor=request.user, action="DEPARTMENT_DELETE",
                target_model="Department", target_id=str(pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"name": dept_name},
            )
        messages.success(request, f"Department '{dept_name}' deleted successfully.")
        return redirect("employees:department_list")



class ShiftListView(AccountantOrSuperadminMixin, ListView):
    model = Shift
    template_name = "employees/shift_list.html"
    context_object_name = "shifts"


class ShiftCreateView(AccountantOrSuperadminMixin, View):
    def get(self, request):
        return render(request, "employees/lookup_form.html", {"form": ShiftForm(), "title": "Add Shift"})

    def post(self, request):
        form = ShiftForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Shift created.")
            return redirect("employees:shift_list")
        return render(request, "employees/lookup_form.html", {"form": form, "title": "Add Shift"})


class ShiftDeleteView(AccountantOrSuperadminMixin, View):
    template_name = "employees/shift_confirm_delete.html"

    def get(self, request, pk):
        shift = get_object_or_404(Shift, pk=pk)
        return render(request, self.template_name, {
            "shift": shift,
            "employee_count": shift.employees.count(),
        })

    def post(self, request, pk):
        shift = get_object_or_404(Shift, pk=pk)
        shift_name = shift.name
        emp_count = shift.employees.count()
        with transaction.atomic():
            shift.delete()
            audit_log(
                actor=request.user, action="SHIFT_DELETE",
                target_model="Shift", target_id=str(pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={"name": shift_name, "unassigned_employees": emp_count},
            )
        if emp_count > 0:
            messages.success(
                request,
                f"Shift '{shift_name}' deleted successfully. {emp_count} employee(s) who had this shift have been unassigned."
            )
        else:
            messages.success(request, f"Shift '{shift_name}' deleted successfully.")
        return redirect("employees:shift_list")

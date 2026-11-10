"""Thamarayyath Employee Portal — Payroll Views."""

import logging
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView

from accounts.permissions import AnyRoleMixin, AccountantOrSuperadminMixin, AccountantRequiredMixin
from audit.services import audit_log
from employees.models import Employee, Department
from .forms import GeneratePayrollForm, PayrollReviewForm, PayrollFinalizeForm
from .models import PayrollPeriod, PayrollStatement, PayrollStatus
from .services import generate_payroll_period, finalize_payroll_period

logger = logging.getLogger("portal")


class PayrollPeriodListView(AnyRoleMixin, ListView):
    model = PayrollPeriod
    template_name = "payroll/period_list.html"
    context_object_name = "periods"
    paginate_by = 20
    queryset = PayrollPeriod.objects.order_by("-start_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = PayrollStatus.choices
        return ctx


class PayrollPeriodDetailView(AnyRoleMixin, View):
    template_name = "payroll/period_detail.html"

    def get(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        statements = (
            PayrollStatement.objects
            .filter(payroll_period=period)
            .select_related("employee", "employee__department")
            .prefetch_related("line_items")
            .order_by("employee__employee_id")
        )
        totals = statements.aggregate(
            total_gross=Sum("gross_pay"),
            total_net=Sum("net_pay"),
            total_overtime=Sum("overtime_pay"),
        )
        # Owner cannot see individual salary breakdowns — only totals
        if request.user.is_owner:
            statements = None  # Will show aggregate only in template
        return render(request, self.template_name, {
            "period": period,
            "statements": statements,
            "totals": totals,
            "can_review": not request.user.is_owner and period.status == PayrollStatus.DRAFT,
            "can_finalize": not request.user.is_owner and period.status == PayrollStatus.REVIEWED,
        })


class GeneratePayrollView(AccountantOrSuperadminMixin, View):
    template_name = "payroll/generate.html"

    def get(self, request):
        form = GeneratePayrollForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = GeneratePayrollForm(request.POST)
        if form.is_valid():
            try:
                dept = form.cleaned_data.get("department")
                period = generate_payroll_period(
                    cycle_type=form.cleaned_data["cycle_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    requested_by=request.user,
                    notes=form.cleaned_data.get("notes", ""),
                    department=dept,
                )
                audit_log(
                    actor=request.user, action="PAYROLL_GENERATE",
                    target_model="PayrollPeriod", target_id=str(period.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "cycle": period.cycle_type,
                        "start": str(period.start_date),
                        "end": str(period.end_date),
                        "department": dept.name if dept else "All Departments",
                    },
                )
                messages.success(
                    request,
                    f"Payroll generated for {period.get_cycle_type_display()} "
                    f"{period.start_date} – {period.end_date} "
                    f"({period.statements.count()} employees)."
                )
                return redirect("payroll:period_detail", pk=period.pk)
            except ValueError as e:
                form.add_error(None, str(e))
        return render(request, self.template_name, {"form": form})


class ReviewPayrollView(AccountantOrSuperadminMixin, View):
    template_name = "payroll/review.html"

    def get(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollStatus.DRAFT:
            messages.error(request, "Only DRAFT payroll periods can be reviewed.")
            return redirect("payroll:period_detail", pk=pk)
        return render(request, self.template_name, {
            "period": period,
            "form": PayrollReviewForm(),
            "statements": period.statements.select_related("employee").all(),
        })

    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollStatus.DRAFT:
            raise PermissionDenied("Cannot review a non-DRAFT payroll.")
        form = PayrollReviewForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                period.status = PayrollStatus.REVIEWED
                period.reviewed_by = request.user
                period.reviewed_at = timezone.now()
                if form.cleaned_data.get("notes"):
                    period.notes += f"\nReviewer: {form.cleaned_data['notes']}"
                period.save()
                PayrollStatement.objects.filter(payroll_period=period).update(
                    status=PayrollStatus.REVIEWED
                )
                audit_log(
                    actor=request.user, action="PAYROLL_REVIEW",
                    target_model="PayrollPeriod", target_id=str(period.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
            messages.success(request, "Payroll period marked as Reviewed.")
            return redirect("payroll:period_detail", pk=pk)
        return render(request, self.template_name, {"period": period, "form": form})


class FinalizePayrollView(AccountantOrSuperadminMixin, View):
    template_name = "payroll/finalize.html"

    def get(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollStatus.REVIEWED:
            messages.error(request, "Only REVIEWED payroll periods can be finalized.")
            return redirect("payroll:period_detail", pk=pk)
        return render(request, self.template_name, {
            "period": period,
            "form": PayrollFinalizeForm(),
        })

    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        form = PayrollFinalizeForm(request.POST)
        if form.is_valid():
            try:
                period = finalize_payroll_period(period, finalized_by=request.user)
                audit_log(
                    actor=request.user, action="PAYROLL_FINALIZE",
                    target_model="PayrollPeriod", target_id=str(period.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, "Payroll finalized. Attendance records are now locked.")
                return redirect("payroll:period_detail", pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
        return render(request, self.template_name, {"period": period, "form": form})


class StatementDetailView(AnyRoleMixin, View):
    template_name = "payroll/statement_detail.html"

    def get(self, request, pk):
        stmt = get_object_or_404(
            PayrollStatement.objects.select_related(
                "employee", "payroll_period", "finalized_by"
            ).prefetch_related("line_items"),
            pk=pk,
        )
        # Owner can view, but not the raw breakdown JSON
        show_breakdown = not request.user.is_owner
        return render(request, self.template_name, {
            "statement": stmt,
            "show_breakdown": show_breakdown,
        })


class WageDisbursementGlobalView(AccountantOrSuperadminMixin, View):
    """Global index of payroll periods and wage disbursement statuses."""
    template_name = "payroll/wage_disbursement_global.html"

    def get(self, request):
        periods = PayrollPeriod.objects.prefetch_related("statements").order_by("-start_date")
        return render(request, self.template_name, {"periods": periods})


class WageDisbursementView(AccountantOrSuperadminMixin, View):
    """
    Dedicated page to view and mark whether wages have been paid or are pending
    for each employee in a specific payroll period.
    """
    template_name = "payroll/wage_disbursement.html"

    def get(self, request, period_pk):
        period = get_object_or_404(PayrollPeriod, pk=period_pk)
        status_filter = request.GET.get("status", "all").lower()

        statements_qs = (
            PayrollStatement.objects
            .filter(payroll_period=period)
            .select_related("employee", "employee__department", "employee__designation", "paid_by")
            .order_by("is_paid", "employee__employee_id")
        )

        if status_filter == "paid":
            statements = statements_qs.filter(is_paid=True)
        elif status_filter == "unpaid":
            statements = statements_qs.filter(is_paid=False)
        else:
            statements = statements_qs

        total_count = period.statements.count()
        paid_count = period.total_paid_count
        unpaid_count = period.total_unpaid_count
        paid_pct = round((paid_count / total_count * 100), 1) if total_count > 0 else 0

        return render(request, self.template_name, {
            "period": period,
            "statements": statements,
            "status_filter": status_filter,
            "total_count": total_count,
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
            "paid_pct": paid_pct,
            "total_payable": period.total_net_pay,
            "total_paid": period.total_paid_amount,
            "total_unpaid": period.total_unpaid_amount,
        })


class WageMarkPaidToggleView(AccountantOrSuperadminMixin, View):
    """
    Toggle paid/unpaid status for an individual employee's wage statement.
    """
    def post(self, request, pk):
        stmt = get_object_or_404(
            PayrollStatement.objects.select_related("employee", "payroll_period"),
            pk=pk,
        )
        action = request.POST.get("action", "mark_paid")
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or redirect("payroll:period_payments", period_pk=stmt.payroll_period.pk)

        if action == "mark_paid":
            method = request.POST.get("payment_method", "BANK_TRANSFER")
            remarks = request.POST.get("payment_remarks", "").strip()
            with transaction.atomic():
                stmt.mark_paid(by_user=request.user, method=method, remarks=remarks)
                audit_log(
                    actor=request.user, action="WAGE_PAYMENT_UPDATE",
                    target_model="PayrollStatement", target_id=str(stmt.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "employee_id": stmt.employee.employee_id,
                        "status": "PAID",
                        "method": method,
                        "amount": str(stmt.net_pay),
                    },
                )
            messages.success(
                request,
                f"Wage of ₹{stmt.net_pay} for {stmt.employee.full_name} marked as PAID ({stmt.get_payment_method_display()})."
            )
        else:
            with transaction.atomic():
                stmt.mark_unpaid()
                audit_log(
                    actor=request.user, action="WAGE_PAYMENT_UPDATE",
                    target_model="PayrollStatement", target_id=str(stmt.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "employee_id": stmt.employee.employee_id,
                        "status": "UNPAID",
                        "amount": str(stmt.net_pay),
                    },
                )
            messages.info(request, f"Wage payment for {stmt.employee.full_name} reverted to UNPAID.")

        if isinstance(next_url, str):
            return redirect(next_url)
        return next_url


class WageBulkMarkPaidView(AccountantOrSuperadminMixin, View):
    """
    Bulk marks all unpaid statements in a payroll period as paid.
    """
    def post(self, request, period_pk):
        period = get_object_or_404(PayrollPeriod, pk=period_pk)
        method = request.POST.get("payment_method", "BANK_TRANSFER")
        remarks = request.POST.get("payment_remarks", "Bulk disbursement").strip()

        unpaid_stmts = period.statements.filter(is_paid=False)
        count = unpaid_stmts.count()

        if count == 0:
            messages.info(request, "All employee wages for this period are already marked as Paid.")
            return redirect("payroll:period_payments", period_pk=period.pk)

        with transaction.atomic():
            for stmt in unpaid_stmts:
                stmt.mark_paid(by_user=request.user, method=method, remarks=remarks)

            audit_log(
                actor=request.user, action="WAGE_BULK_PAYMENT",
                target_model="PayrollPeriod", target_id=str(period.pk),
                ip_address=request.META.get("REMOTE_ADDR"),
                extra={
                    "period_id": period.pk,
                    "count": count,
                    "method": method,
                },
            )

        messages.success(request, f"Successfully marked {count} employee wage statement(s) as PAID via {method}.")
        return redirect("payroll:period_payments", period_pk=period.pk)

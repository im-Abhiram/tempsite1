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
                period = generate_payroll_period(
                    cycle_type=form.cleaned_data["cycle_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    requested_by=request.user,
                    notes=form.cleaned_data.get("notes", ""),
                )
                audit_log(
                    actor=request.user, action="PAYROLL_GENERATE",
                    target_model="PayrollPeriod", target_id=str(period.pk),
                    ip_address=request.META.get("REMOTE_ADDR"),
                    extra={
                        "cycle": period.cycle_type,
                        "start": str(period.start_date),
                        "end": str(period.end_date),
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

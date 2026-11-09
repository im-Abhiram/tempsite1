"""Thamarayyath Employee Portal — Payroll URL Configuration."""
from django.urls import path
from . import views

app_name = "payroll"

urlpatterns = [
    path("", views.PayrollPeriodListView.as_view(), name="period_list"),
    path("generate/", views.GeneratePayrollView.as_view(), name="generate"),
    path("<int:pk>/", views.PayrollPeriodDetailView.as_view(), name="period_detail"),
    path("<int:pk>/review/", views.ReviewPayrollView.as_view(), name="review"),
    path("<int:pk>/finalize/", views.FinalizePayrollView.as_view(), name="finalize"),
    path("statement/<int:pk>/", views.StatementDetailView.as_view(), name="statement_detail"),
    # Wage Disbursement & Payment Tracking
    path("payments/", views.WageDisbursementGlobalView.as_view(), name="payment_dashboard"),
    path("<int:period_pk>/payments/", views.WageDisbursementView.as_view(), name="period_payments"),
    path("<int:period_pk>/bulk-pay/", views.WageBulkMarkPaidView.as_view(), name="bulk_mark_paid"),
    path("statement/<int:pk>/toggle-payment/", views.WageMarkPaidToggleView.as_view(), name="toggle_payment"),
]

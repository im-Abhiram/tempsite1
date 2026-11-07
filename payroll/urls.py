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
]

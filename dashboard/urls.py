"""
Thamarayyath Employee Portal — Dashboard URL Configuration.
"""

from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardRouterView.as_view(), name="home"),
    path("superadmin/", views.SuperadminDashboardView.as_view(), name="superadmin"),
    path("accountant/", views.AccountantDashboardView.as_view(), name="accountant"),
    path("owner/", views.OwnerDashboardView.as_view(), name="owner"),
]


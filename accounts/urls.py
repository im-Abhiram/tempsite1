"""Thamarayyath Employee Portal — Accounts URL Configuration."""

from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("change-password/", views.ChangeOwnPasswordView.as_view(), name="change_password"),

    # User management (Superadmin only)
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/create/", views.CreateUserView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.EditUserView.as_view(), name="user_edit"),
    path("users/<int:pk>/suspend/", views.SuspendUserView.as_view(), name="user_suspend"),
    path("users/<int:pk>/activate/", views.ActivateUserView.as_view(), name="user_activate"),
    path("users/<int:pk>/reset-password/", views.ResetUserPasswordView.as_view(), name="user_reset_password"),

    # Company settings (Superadmin only)
    path("settings/", views.CompanySettingsView.as_view(), name="company_settings"),
]

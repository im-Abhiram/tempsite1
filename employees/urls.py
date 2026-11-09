"""Thamarayyath Employee Portal — Employees URL Configuration."""

from django.urls import path
from . import views

app_name = "employees"

urlpatterns = [
    # Dashboard (role-aware)
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("", views.DashboardView.as_view(), name="home"),

    # Employees
    path("employees/", views.EmployeeListView.as_view(), name="employee_list"),
    path("employees/create/", views.EmployeeCreateView.as_view(), name="employee_create"),
    path("employees/<int:pk>/", views.EmployeeDetailView.as_view(), name="employee_detail"),
    path("employees/<int:pk>/edit/", views.EmployeeUpdateView.as_view(), name="employee_edit"),
    path("employees/<int:pk>/delete/", views.EmployeeDeleteView.as_view(), name="employee_delete"),
    path("employees/<int:pk>/salary/", views.SalaryUpdateView.as_view(), name="salary_update"),

    # Documents
    path("employees/<int:pk>/documents/upload/", views.DocumentUploadView.as_view(), name="document_upload"),
    path("documents/<int:doc_pk>/download/", views.DocumentServeView.as_view(), name="document_download"),

    # Departments
    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("departments/create/", views.DepartmentCreateView.as_view(), name="department_create"),
    path("departments/<int:pk>/delete/", views.DepartmentDeleteView.as_view(), name="department_delete"),

    # Shifts
    path("shifts/", views.ShiftListView.as_view(), name="shift_list"),
    path("shifts/create/", views.ShiftCreateView.as_view(), name="shift_create"),
    path("shifts/<int:pk>/delete/", views.ShiftDeleteView.as_view(), name="shift_delete"),
]

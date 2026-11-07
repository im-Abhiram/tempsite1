"""Thamarayyath Employee Portal — employees app config."""
from django.apps import AppConfig

class EmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employees"
    verbose_name = "Employee Management"

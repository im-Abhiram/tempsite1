"""
Thamarayyath Employee Portal — Root URL Configuration
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Authentication
    path("accounts/", include("accounts.urls", namespace="accounts")),
    # Dashboard & Core Administration
    path("dashboard/", include("dashboard.urls", namespace="dashboard")),
    path("core/", include("core.urls", namespace="core")),
    # Core modules
    path("", include("employees.urls", namespace="employees")),
    path("attendance/", include("attendance.urls", namespace="attendance")),
    path("payroll/", include("payroll.urls", namespace="payroll")),
    path("reports/", include("reports.urls", namespace="reports")),
    path("audit/", include("audit.urls", namespace="audit")),
]

# Serve public media (employee photos) in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# NOTE: Django Admin is intentionally excluded.
# Management is performed via the custom Superadmin interface.
# If admin must be enabled, set ADMIN_URL to a secret path in settings.

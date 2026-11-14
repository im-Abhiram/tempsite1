"""
Thamarayyath Employee Portal — Project Settings
Loads all configuration from environment variables (.env) via python-dotenv.
"""

from pathlib import Path
import os
import sys
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Detect if automated tests are currently running
TESTING = "test" in sys.argv

# Load .env file
load_dotenv(BASE_DIR / ".env")

# ─── Core Security ─────────────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

_raw_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

_raw_csrf = os.getenv(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
)
CSRF_TRUSTED_ORIGINS = [h.strip() for h in _raw_csrf.split(",") if h.strip()]

# ─── Applications ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Django Core
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Portal Apps
    "accounts.apps.AccountsConfig",
    "employees.apps.EmployeesConfig",
    "attendance.apps.AttendanceConfig",
    "payroll.apps.PayrollConfig",
    "audit.apps.AuditConfig",
    "reports.apps.ReportsConfig",
    "core.apps.CoreConfig",
    "dashboard.apps.DashboardConfig",
]

# ─── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom: Security Headers (CSP, Permissions-Policy, CORP, COEP, X-XSS)
    "accounts.middleware.SecurityHeadersMiddleware",
    # Custom: login throttling + idle timeout + audit context
    "accounts.middleware.LoginThrottleMiddleware",
    "accounts.middleware.IdleSessionTimeoutMiddleware",
    "accounts.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

# ─── Templates ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.portal_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ─── Database ──────────────────────────────────────────────────────────────────
_db_url = os.getenv("DATABASE_URL")
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

# Always ensure SQLite uses the persistent absolute path in BASE_DIR on PythonAnywhere
if DATABASES["default"].get("ENGINE") == "django.db.backends.sqlite3":
    db_name = str(DATABASES["default"].get("NAME", "db.sqlite3"))
    if not Path(db_name).is_absolute() or db_name == "db.sqlite3":
        DATABASES["default"]["NAME"] = str(BASE_DIR / Path(db_name).name)

# Ensure atomic requests to protect payroll multi-step transactions
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# ─── Custom User Model ──────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.CustomUser"

# ─── Authentication ─────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = ["accounts.backends.ThrottledModelBackend"]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("username", "email"), "max_similarity": 0.7},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Session Security ───────────────────────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "3600"))  # 1 hour idle
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # True in production (HTTPS)
SESSION_SAVE_EVERY_REQUEST = True  # rolling idle timer
IDLE_SESSION_TIMEOUT = int(os.getenv("SESSION_COOKIE_AGE", "3600"))

# ─── CSRF ───────────────────────────────────────────────────────────────────────
CSRF_COOKIE_HTTPONLY = True  # Strict HTTP-only cookie prevents XSS token theft
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG

# ─── HTTP Security Headers ──────────────────────────────────────────────────────
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# Disabled legacy XSS auditor filter to prevent known browser side-channel vulnerabilities;
# X-XSS-Protection: 0 and strict Content-Security-Policy (CSP) are enforced in SecurityHeadersMiddleware.
SECURE_BROWSER_XSS_FILTER = False
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# CSP and COEP Configuration
CSP_REPORT_ONLY = os.getenv("DJANGO_CSP_REPORT_ONLY", "False").lower() in ("true", "1")
COEP_POLICY = os.getenv("DJANGO_COEP_POLICY", "unsafe-none")

# Enforce HTTPS headers in production
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "True").lower() in ("true", "1")
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "False").lower() in ("true", "1")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ─── Internationalisation ───────────────────────────────────────────────────────
LANGUAGE_CODE = os.getenv("LANGUAGE_CODE", "en-us")
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True  # Store all datetimes as UTC; convert to TIME_ZONE for display

# ─── Static Files ──────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ─── Media Files & Document Storage ────────────────────────────────────────────
# Public media (photos only)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
EMPLOYEE_PHOTOS_ROOT = MEDIA_ROOT / "employee_photos"
EMPLOYEE_DOCUMENTS_ROOT = MEDIA_ROOT / "employee_documents"
PAYROLL_DOCUMENTS_ROOT = MEDIA_ROOT / "payroll_documents"
PRIVATE_VAULT_ROOT = EMPLOYEE_DOCUMENTS_ROOT  # Backward compatibility pointer

MAX_UPLOAD_SIZE_MB = 10
ALLOWED_DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".xlsx"}
ALLOWED_DOC_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Create required application directories automatically
for _d in (
    BASE_DIR / "logs",
    MEDIA_ROOT,
    EMPLOYEE_PHOTOS_ROOT,
    EMPLOYEE_DOCUMENTS_ROOT,
    PAYROLL_DOCUMENTS_ROOT,
    BASE_DIR / "private_vault",
):
    _d.mkdir(parents=True, exist_ok=True)

# ─── Default Primary Key Field ──────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Login Rate Limiting ────────────────────────────────────────────────────────
MAX_FAILED_LOGINS = 5
LOGIN_LOCKOUT_MINUTES = 15

# ─── Logging ────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {asctime} {message}", "style": "{"},
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "portal.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 10,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "portal": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["file"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["file"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# Create logs directory if it doesn't exist
(BASE_DIR / "logs").mkdir(exist_ok=True)
(BASE_DIR / "private_vault").mkdir(exist_ok=True)

# ─── Application-Level Payroll Constants ────────────────────────────────────────
DECIMAL_PLACES = 2

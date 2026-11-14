"""
Thamarayyath Employee Portal — Security Middleware Stack.

LoginThrottleMiddleware    — Blocks requests from accounts that are currently locked.
IdleSessionTimeoutMiddleware — Expires sessions after configurable idle period.
AuditContextMiddleware     — Attaches the remote IP to the current thread for audit logging.
"""

import ipaddress
import logging
import secrets
import threading
import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger("portal")
_audit_context = threading.local()


def clean_ip(ip_str):
    """
    Validate and return a normalized IPv4/IPv6 address string, or None if invalid.
    Guarantees that malformed IP strings from headers never crash GenericIPAddressField.
    """
    if not ip_str:
        return None
    try:
        ip_obj = ipaddress.ip_address(str(ip_str).strip())
        return str(ip_obj)
    except (ValueError, TypeError, AttributeError):
        return None


def get_current_ip():
    """Retrieve the IP address stored by AuditContextMiddleware for the current thread."""
    return getattr(_audit_context, "ip_address", None)


class LoginThrottleMiddleware:
    """
    Intercept every authenticated request and verify the account is not locked or deactivated.
    This ensures that an admin who suspends an account mid-session invalidates it immediately.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Re-fetch from DB to detect real-time suspension
            try:
                user = request.user.__class__.objects.get(pk=request.user.pk)
            except request.user.__class__.DoesNotExist:
                logout(request)
                return redirect(settings.LOGIN_URL)

            if not user.is_active or user.is_locked():
                logout(request)
                logger.warning(
                    "Active session terminated: username=%s reason=account_suspended_or_locked",
                    request.user.username,
                )
                return redirect(settings.LOGIN_URL + "?suspended=1")

        response = self.get_response(request)
        return response


class IdleSessionTimeoutMiddleware:
    """
    Expire sessions that have been idle beyond IDLE_SESSION_TIMEOUT seconds.
    Uses 'last_activity' stored in the session for accurate tracking.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "IDLE_SESSION_TIMEOUT", 3600)

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get("_last_activity")
            now = int(time.time())
            if last_activity and (now - last_activity) > self.timeout:
                logout(request)
                logger.info(
                    "Session expired due to inactivity: username=%s",
                    request.user.username,
                )
                return redirect(settings.LOGIN_URL + "?timeout=1")
            request.session["_last_activity"] = now

        response = self.get_response(request)
        return response


class AuditContextMiddleware:
    """
    Attach the client's IP address to the current thread so that service
    functions and signal handlers can record it in audit log entries without
    requiring an explicit request argument.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = self._get_client_ip(request)
        _audit_context.ip_address = ip
        response = self.get_response(request)
        _audit_context.ip_address = None
        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            for part in x_forwarded_for.split(","):
                valid_ip = clean_ip(part.strip())
                if valid_ip:
                    return valid_ip
        remote_addr = request.META.get("REMOTE_ADDR")
        return clean_ip(remote_addr) or "127.0.0.1"


class SecurityHeadersMiddleware:
    """
    Enforces modern HTTP defense-in-depth security headers across all responses.

    1. Content-Security-Policy (CSP) with dynamic per-request cryptographic nonces
    2. Permissions-Policy (restricts sensitive device & browser APIs)
    3. Cross-Origin-Resource-Policy (CORP: same-origin)
    4. Cross-Origin-Embedder-Policy (COEP: unsafe-none to safely allow Google Fonts / CDNs)
    5. Cross-Origin-Opener-Policy (COOP: same-origin)
    6. X-XSS-Protection (0: modern OWASP standard disabling buggy legacy XSS auditors)
    7. X-Content-Type-Options (nosniff)
    8. X-Frame-Options (DENY)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.report_only = getattr(settings, "CSP_REPORT_ONLY", False)
        self.coep_policy = getattr(settings, "COEP_POLICY", "unsafe-none")

    def __call__(self, request):
        # Generate a cryptographically secure 128-bit random nonce for this request
        request.csp_nonce = secrets.token_urlsafe(16)

        response = self.get_response(request)

        # 1. Content-Security-Policy
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{request.csp_nonce}' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: blob:",
            "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "connect-src 'self'",
            "media-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        if not settings.DEBUG and request.is_secure():
            csp_directives.append("upgrade-insecure-requests")

        csp_header = "; ".join(csp_directives)
        header_name = "Content-Security-Policy-Report-Only" if self.report_only else "Content-Security-Policy"
        response[header_name] = csp_header

        # 2. Permissions-Policy: Restrict camera, mic, geolocation, payment, USB, etc.
        response["Permissions-Policy"] = (
            "accelerometer=(), "
            "autoplay=(), "
            "camera=(), "
            "display-capture=(), "
            "encrypted-media=(), "
            "fullscreen=(self), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "midi=(), "
            "payment=(), "
            "usb=()"
        )

        # 3. Cross-Origin-Resource-Policy: Disallow embedding on cross-origin sites
        response["Cross-Origin-Resource-Policy"] = "same-origin"

        # 4. Cross-Origin-Embedder-Policy: 'unsafe-none' allows third-party CDNs without CORP
        response["Cross-Origin-Embedder-Policy"] = self.coep_policy

        # 5. Cross-Origin-Opener-Policy: Isolates browsing context from external windows
        if "Cross-Origin-Opener-Policy" not in response:
            response["Cross-Origin-Opener-Policy"] = "same-origin"

        # 6. X-XSS-Protection: Modern OWASP recommendation is 0 (disables vulnerable legacy browser filter)
        response["X-XSS-Protection"] = "0"

        # 7. Ensure X-Content-Type-Options: nosniff
        if "X-Content-Type-Options" not in response:
            response["X-Content-Type-Options"] = "nosniff"

        # 8. Ensure X-Frame-Options: DENY
        if "X-Frame-Options" not in response:
            response["X-Frame-Options"] = "DENY"

        return response

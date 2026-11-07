"""
Thamarayyath Employee Portal — Security Middleware Stack.

LoginThrottleMiddleware    — Blocks requests from accounts that are currently locked.
IdleSessionTimeoutMiddleware — Expires sessions after configurable idle period.
AuditContextMiddleware     — Attaches the remote IP to the current thread for audit logging.
"""

import logging
import threading
import time
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger("portal")
_audit_context = threading.local()


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
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "127.0.0.1")

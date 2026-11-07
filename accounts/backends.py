"""
Thamarayyath Employee Portal — Authentication Backend.

Uses a throttled backend that checks account lock state before authenticating.
This replaces Django's default ModelBackend to add rate-limit enforcement.
"""

import logging
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.conf import settings

logger = logging.getLogger("portal")
User = get_user_model()


class ThrottledModelBackend(ModelBackend):
    """
    Custom authentication backend that:
    1. Checks account lock state before attempting password validation.
    2. Records failed attempts and locks account after threshold.
    3. Does NOT reveal whether the username exists (uniform error message).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        max_attempts = getattr(settings, "MAX_FAILED_LOGINS", 5)
        lockout_minutes = getattr(settings, "LOGIN_LOCKOUT_MINUTES", 15)

        try:
            user = User.objects.get(username=username.strip().lower())
        except User.DoesNotExist:
            # Constant-time dummy check to resist timing attacks
            User().check_password(password)
            logger.warning(
                "Login attempt for non-existent user: username=%s ip=%s",
                username,
                getattr(request, "META", {}).get("REMOTE_ADDR", "unknown"),
            )
            return None

        # Check if account is locked
        if user.is_locked():
            logger.warning(
                "Login attempt on locked account: username=%s ip=%s",
                username,
                getattr(request, "META", {}).get("REMOTE_ADDR", "unknown"),
            )
            return None

        # Check if account is active
        if not user.is_active:
            logger.warning(
                "Login attempt on inactive account: username=%s ip=%s",
                username,
                getattr(request, "META", {}).get("REMOTE_ADDR", "unknown"),
            )
            return None

        # Validate password
        if user.check_password(password):
            return user

        # Record failed attempt
        ip = getattr(request, "META", {}).get("REMOTE_ADDR", "unknown")
        user.record_failed_login(max_attempts, lockout_minutes)
        logger.warning(
            "Failed login: username=%s ip=%s attempts=%d",
            username,
            ip,
            user.failed_login_attempts,
        )
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

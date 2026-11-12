"""
Thamarayyath Employee Portal — RBAC Decorators, Mixins, and Permission Utilities.

All permission checks are enforced server-side.
Frontend hiding of buttons is never the sole access control mechanism.
"""

import functools
import logging
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.conf import settings
from .models import Role

logger = logging.getLogger("portal")


# ─── Function-Based View Decorators ────────────────────────────────────────────

def login_required_portal(view_func):
    """Redirect unauthenticated users to login."""
    @functools.wraps(view_func)
    def _wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return view_func(request, *args, **kwargs)
    return _wrapper


def role_required(*roles):
    """
    Decorator factory: require the authenticated user to have one of the given roles.
    Raises PermissionDenied (→ 403) rather than redirecting, to avoid leaking
    information about which URLs exist.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            effective_roles = set(roles)
            if Role.OFFICE_ADMIN in effective_roles or "ACCOUNTANT" in effective_roles:
                effective_roles.add(Role.OFFICE_ADMIN)
                effective_roles.add("ACCOUNTANT")
            if request.user.role not in effective_roles:
                logger.warning(
                    "Permission denied: user=%s role=%s required=%s path=%s",
                    request.user.username, request.user.role, roles, request.path,
                )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapper
    return decorator


def superadmin_required(view_func):
    return role_required(Role.SUPERADMIN)(view_func)


def office_admin_required(view_func):
    return role_required(Role.OFFICE_ADMIN)(view_func)


def accountant_required(view_func):
    return office_admin_required(view_func)


def office_admin_or_superadmin(view_func):
    return role_required(Role.OFFICE_ADMIN, Role.SUPERADMIN)(view_func)


def accountant_or_superadmin(view_func):
    return office_admin_or_superadmin(view_func)


def not_owner(view_func):
    """Deny access to Owner role (modification endpoints)."""
    return role_required(Role.SUPERADMIN, Role.OFFICE_ADMIN)(view_func)


# ─── Class-Based View Mixins ────────────────────────────────────────────────────

class PortalLoginRequiredMixin(LoginRequiredMixin):
    login_url = "/accounts/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(PortalLoginRequiredMixin):
    """
    Mixin for class-based views. Set `required_roles` as a list of Role values.
    Example:
        required_roles = [Role.SUPERADMIN]
    """
    required_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        effective_roles = set(self.required_roles)
        if Role.OFFICE_ADMIN in effective_roles or "ACCOUNTANT" in effective_roles:
            effective_roles.add(Role.OFFICE_ADMIN)
            effective_roles.add("ACCOUNTANT")
        if self.required_roles and request.user.role not in effective_roles:
            logger.warning(
                "Permission denied: user=%s role=%s required=%s path=%s",
                request.user.username, request.user.role,
                self.required_roles, request.path,
            )
            raise PermissionDenied
        return super(PortalLoginRequiredMixin, self).dispatch(request, *args, **kwargs)


class SuperadminRequiredMixin(RoleRequiredMixin):
    required_roles = [Role.SUPERADMIN]


class OfficeAdminRequiredMixin(RoleRequiredMixin):
    required_roles = [Role.OFFICE_ADMIN]


class AccountantRequiredMixin(OfficeAdminRequiredMixin):
    pass


class OfficeAdminOrSuperadminMixin(RoleRequiredMixin):
    required_roles = [Role.OFFICE_ADMIN, Role.SUPERADMIN]


class AccountantOrSuperadminMixin(OfficeAdminOrSuperadminMixin):
    pass


class NotOwnerMixin(RoleRequiredMixin):
    """Allow Superadmin and Office Administration; deny Owner."""
    required_roles = [Role.SUPERADMIN, Role.OFFICE_ADMIN]


class AnyRoleMixin(PortalLoginRequiredMixin):
    """Any authenticated user is allowed (still requires login)."""
    pass


# ─── Object-Level Permission Helpers ───────────────────────────────────────────

def assert_can_view_employee(user, employee):
    """
    Raise PermissionDenied if user cannot view the given employee.
    All authenticated roles can view; this is a hook for future data isolation.
    """
    if not user.is_authenticated:
        raise PermissionDenied


def assert_can_edit_employee(user, employee):
    """Raise PermissionDenied if user is not allowed to edit employee records."""
    if user.role not in (Role.SUPERADMIN, Role.OFFICE_ADMIN, "ACCOUNTANT"):
        raise PermissionDenied


def assert_can_manage_accounts(user):
    """Only Superadmin may manage user accounts."""
    if user.role != Role.SUPERADMIN:
        raise PermissionDenied


def assert_cannot_self_promote(requesting_user, target_user, new_role):
    """Prevent any user from assigning a higher or different role to themselves."""
    if requesting_user.pk == target_user.pk:
        raise PermissionDenied("Users cannot modify their own role.")
    if requesting_user.role != Role.SUPERADMIN:
        raise PermissionDenied("Only a Superadmin can assign roles.")

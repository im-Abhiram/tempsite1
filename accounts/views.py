"""
Thamarayyath Employee Portal — Account Views.
Handles authentication, account management (Superadmin), and password changes.
"""

import logging
from django.contrib.auth import login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import ListView
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from .forms import (
    PortalLoginForm, CreateUserForm, EditUserForm,
    ResetPasswordForm, ChangeOwnPasswordForm, CompanySettingsForm,
)
from .models import CompanySettings, Role
from .permissions import (
    PortalLoginRequiredMixin, SuperadminRequiredMixin,
    AnyRoleMixin, assert_cannot_self_promote, assert_can_manage_accounts,
)
from audit.services import audit_log

logger = logging.getLogger("portal")
User = get_user_model()


# ─── Authentication Views ───────────────────────────────────────────────────────

class CaptchaImageView(View):
    """
    Renders dynamic CAPTCHA security image for the login page.
    Generates a 5-character distorted image and stores the answer in session.
    """
    def get(self, request):
        from .captcha import generate_captcha_image
        png_bytes, code = generate_captcha_image(length=5)
        request.session["login_captcha"] = code
        response = HttpResponse(png_bytes, content_type="image/png")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


class LoginView(View):
    template_name = "accounts/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("employees:dashboard")
        form = PortalLoginForm(request)
        ctx = {
            "form": form,
            "suspended": request.GET.get("suspended"),
            "timeout": request.GET.get("timeout"),
        }
        return render(request, self.template_name, ctx)

    def post(self, request):
        form = PortalLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Clear used CAPTCHA from session
            request.session.pop("login_captcha", None)
            # Rotate session to prevent fixation
            request.session.cycle_key()
            login(request, user, backend="accounts.backends.ThrottledModelBackend")
            ip = request.META.get("REMOTE_ADDR", "unknown")
            user.record_successful_login(ip_address=ip)
            audit_log(
                actor=user, action="LOGIN_SUCCESS",
                target_model="CustomUser", target_id=str(user.pk),
                ip_address=ip,
            )
            logger.info("Successful login: username=%s ip=%s", user.username, ip)
            next_url = request.GET.get("next", "")
            # Validate next URL to prevent open redirect
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect("employees:dashboard")

        # Log failed form submission (invalid username/password or captcha)
        ip = request.META.get("REMOTE_ADDR", "unknown")
        attempted_username = request.POST.get("username", "")
        audit_log(
            actor=None, action="LOGIN_FAIL",
            target_model="CustomUser", target_id=attempted_username,
            ip_address=ip,
            extra={"reason": "Invalid credentials or verification code"},
        )
        return render(request, self.template_name, {"form": form})


class LogoutView(View):
    def post(self, request):
        if request.user.is_authenticated:
            audit_log(
                actor=request.user, action="LOGOUT",
                target_model="CustomUser", target_id=str(request.user.pk),
                ip_address=request.META.get("REMOTE_ADDR", "unknown"),
            )
            logout(request)
        return redirect("accounts:login")


# ─── Password Change (Any Authenticated User) ───────────────────────────────────

class ChangeOwnPasswordView(AnyRoleMixin, View):
    template_name = "accounts/change_password.html"

    def get(self, request):
        form = ChangeOwnPasswordForm(user=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ChangeOwnPasswordForm(request.POST, user=request.user)
        if form.is_valid():
            new_password = form.cleaned_data["new_password"]
            try:
                validate_password(new_password, request.user)
            except ValidationError as e:
                form.add_error("new_password", e)
                return render(request, self.template_name, {"form": form})

            request.user.set_password(new_password)
            request.user.password_changed_at = timezone.now()
            request.user.save()
            # Keep session valid after password change
            update_session_auth_hash(request, request.user)
            audit_log(
                actor=request.user, action="PASSWORD_CHANGE",
                target_model="CustomUser", target_id=str(request.user.pk),
                ip_address=request.META.get("REMOTE_ADDR", "unknown"),
            )
            messages.success(request, "Your password has been changed successfully.")
            return redirect("employees:dashboard")
        return render(request, self.template_name, {"form": form})


# ─── User Account Management (Superadmin Only) ──────────────────────────────────

class UserListView(SuperadminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.all().order_by("role", "username")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(display_name__icontains=q)
        role = self.request.GET.get("role", "")
        if role in Role.values:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["roles"] = Role.choices
        ctx["active_role"] = self.request.GET.get("role", "")
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


class CreateUserView(SuperadminRequiredMixin, View):
    template_name = "accounts/user_form.html"

    def get(self, request):
        form = CreateUserForm(creating_user=request.user)
        return render(request, self.template_name, {"form": form, "action": "Create"})

    def post(self, request):
        form = CreateUserForm(request.POST, creating_user=request.user)
        if form.is_valid():
            try:
                validate_password(form.cleaned_data["password"])
            except ValidationError as e:
                form.add_error("password", e)
                return render(request, self.template_name, {"form": form, "action": "Create"})

            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password"],
                    role=form.cleaned_data["role"],
                    display_name=form.cleaned_data.get("display_name", ""),
                    email=form.cleaned_data.get("email", ""),
                    created_by=request.user.username,
                )
                audit_log(
                    actor=request.user, action="ACCOUNT_CREATE",
                    target_model="CustomUser", target_id=str(user.pk),
                    ip_address=request.META.get("REMOTE_ADDR", "unknown"),
                    extra={"new_role": user.role, "new_username": user.username},
                )
            messages.success(request, f"Account '{user.username}' created successfully.")
            return redirect("accounts:user_list")
        return render(request, self.template_name, {"form": form, "action": "Create"})


class EditUserView(SuperadminRequiredMixin, View):
    template_name = "accounts/user_form.html"

    def get_target_user(self, pk):
        return get_object_or_404(User, pk=pk)

    def get(self, request, pk):
        target = self.get_target_user(pk)
        form = EditUserForm(
            instance=target,
            editing_user=request.user,
            target_user=target,
        )
        return render(request, self.template_name, {
            "form": form, "action": "Edit", "target_user": target,
        })

    def post(self, request, pk):
        target = self.get_target_user(pk)

        # Prevent self-role change
        if "role" in request.POST and target.pk == request.user.pk:
            raise PermissionDenied("You cannot modify your own role.")

        old_role = target.role
        old_active = target.is_active

        form = EditUserForm(
            request.POST, instance=target,
            editing_user=request.user, target_user=target,
        )
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                changes = {}
                if user.role != old_role:
                    changes["role"] = {"old": old_role, "new": user.role}
                if user.is_active != old_active:
                    changes["is_active"] = {"old": old_active, "new": user.is_active}
                audit_log(
                    actor=request.user, action="ACCOUNT_UPDATE",
                    target_model="CustomUser", target_id=str(user.pk),
                    ip_address=request.META.get("REMOTE_ADDR", "unknown"),
                    extra=changes,
                )
            messages.success(request, f"Account '{target.username}' updated.")
            return redirect("accounts:user_list")
        return render(request, self.template_name, {
            "form": form, "action": "Edit", "target_user": target,
        })


class SuspendUserView(SuperadminRequiredMixin, View):
    """Immediately deactivate (suspend) a user account."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk == request.user.pk:
            raise PermissionDenied("You cannot suspend your own account.")
        if target.role == Role.SUPERADMIN:
            raise PermissionDenied("Cannot suspend another Superadmin via this interface.")
        with transaction.atomic():
            target.is_active = False
            target.save(update_fields=["is_active"])
            audit_log(
                actor=request.user, action="ACCOUNT_SUSPEND",
                target_model="CustomUser", target_id=str(target.pk),
                ip_address=request.META.get("REMOTE_ADDR", "unknown"),
            )
        messages.warning(request, f"Account '{target.username}' has been suspended.")
        return redirect("accounts:user_list")


class ActivateUserView(SuperadminRequiredMixin, View):
    """Reactivate a previously suspended user account."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        with transaction.atomic():
            target.is_active = True
            target.failed_login_attempts = 0
            target.locked_until = None
            target.save(update_fields=["is_active", "failed_login_attempts", "locked_until"])
            audit_log(
                actor=request.user, action="ACCOUNT_ACTIVATE",
                target_model="CustomUser", target_id=str(target.pk),
                ip_address=request.META.get("REMOTE_ADDR", "unknown"),
            )
        messages.success(request, f"Account '{target.username}' has been reactivated.")
        return redirect("accounts:user_list")


class ResetUserPasswordView(SuperadminRequiredMixin, View):
    template_name = "accounts/reset_password.html"

    def get(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        return render(request, self.template_name, {
            "form": ResetPasswordForm(),
            "target_user": target,
        })

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_pw = form.cleaned_data["new_password"]
            try:
                validate_password(new_pw, target)
            except ValidationError as e:
                form.add_error("new_password", e)
                return render(request, self.template_name, {"form": form, "target_user": target})

            with transaction.atomic():
                target.set_password(new_pw)
                target.password_changed_at = timezone.now()
                target.failed_login_attempts = 0
                target.locked_until = None
                target.save()
                audit_log(
                    actor=request.user, action="PASSWORD_RESET",
                    target_model="CustomUser", target_id=str(target.pk),
                    ip_address=request.META.get("REMOTE_ADDR", "unknown"),
                )
            messages.success(request, f"Password reset for '{target.username}' was successful.")
            return redirect("accounts:user_list")
        return render(request, self.template_name, {"form": form, "target_user": target})


# ─── Company Settings ───────────────────────────────────────────────────────────

class CompanySettingsView(SuperadminRequiredMixin, View):
    template_name = "accounts/company_settings.html"

    def get(self, request):
        settings_obj = CompanySettings.get()
        form = CompanySettingsForm(instance=settings_obj)
        return render(request, self.template_name, {"form": form, "settings": settings_obj})

    def post(self, request):
        settings_obj = CompanySettings.get()
        form = CompanySettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.updated_by = request.user
                obj.save()
                audit_log(
                    actor=request.user, action="SETTINGS_UPDATE",
                    target_model="CompanySettings", target_id="1",
                    ip_address=request.META.get("REMOTE_ADDR", "unknown"),
                )
            messages.success(request, "Company settings updated successfully.")
            return redirect("accounts:company_settings")
        return render(request, self.template_name, {"form": form, "settings": settings_obj})

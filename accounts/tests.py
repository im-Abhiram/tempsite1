"""
Thamarayyath Employee Portal — Accounts App Tests.
Covers authentication, role enforcement, lockout policy, and password validation.
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import Role, CompanySettings

User = get_user_model()


class AccountsModelAndAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_superuser(
            username="superadmin",
            password="StrongPassword123!",
            role=Role.SUPERADMIN,
            display_name="Master Superadmin",
            designation="Superadmin",
        )
        self.accountant = User.objects.create_user(
            username="accountant1",
            password="StrongPassword123!",
            role=Role.OFFICE_ADMIN,
            display_name="Lead Administrator",
            designation="Office Administrator",
        )
        self.owner = User.objects.create_user(
            username="owner1",
            password="StrongPassword123!",
            role=Role.OWNER,
            display_name="Business Owner",
            designation="Managing Director",
        )
        self.settings = CompanySettings.get()

    def test_user_role_properties(self):
        self.assertTrue(self.superadmin.is_superadmin)
        self.assertFalse(self.superadmin.is_office_admin)
        self.assertFalse(self.superadmin.is_accountant)
        self.assertFalse(self.superadmin.is_owner)
        self.assertEqual(self.superadmin.designation, "Superadmin")

        self.assertTrue(self.accountant.is_office_admin)
        self.assertTrue(self.accountant.is_accountant)
        self.assertFalse(self.accountant.is_superadmin)
        self.assertEqual(self.accountant.get_role_display(), "Office Administration")
        self.assertEqual(self.accountant.designation, "Office Administrator")

        self.assertTrue(self.owner.is_owner)
        self.assertFalse(self.owner.is_superadmin)
        self.assertEqual(self.owner.designation, "Managing Director")

    def test_successful_login_and_session_cycle(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
        })
        self.assertRedirects(response, reverse("employees:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.accountant.pk)

    def test_failed_login_records_attempts_and_locks_account(self):
        # 5 failed attempts
        for i in range(5):
            self.client.post(reverse("accounts:login"), {
                "username": "accountant1",
                "password": "WrongPassword!",
            })

        self.accountant.refresh_from_db()
        self.assertEqual(self.accountant.failed_login_attempts, 5)
        self.assertTrue(self.accountant.is_locked())

        # Attempting with correct password now fails while locked (uniform message to prevent enumeration)
        response = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password")

    def test_role_based_access_controls(self):
        # Superadmin settings page: accountant forbidden
        self.client.force_login(self.accountant)
        res = self.client.get(reverse("accounts:company_settings"))
        self.assertEqual(res.status_code, 403)

        # Superadmin allowed
        self.client.force_login(self.superadmin)
        res = self.client.get(reverse("accounts:company_settings"))
        self.assertEqual(res.status_code, 200)

        # Owner cannot access user creation
        self.client.force_login(self.owner)
        res = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(res.status_code, 403)

    def test_captcha_generation_and_validation(self):
        """Test mathematical CAPTCHA image generation, invalid code rejection, and valid code acceptance."""
        # 1. Fetch mathematical CAPTCHA image
        res = self.client.get(reverse("accounts:captcha_image"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/png")
        captcha_code = self.client.session.get("login_captcha")
        self.assertTrue(bool(captcha_code))
        # Mathematical answer is a valid integer string
        self.assertTrue(captcha_code.isdigit())

        # 2. Login attempt with WRONG answer fails
        fail_res = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
            "captcha": "999999",
        })
        self.assertEqual(fail_res.status_code, 200)
        self.assertContains(fail_res, "Incorrect answer")

        # 3. Login attempt with CORRECT answer succeeds
        ok_res = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
            "captcha": captcha_code,
        })
        self.assertRedirects(ok_res, reverse("employees:dashboard"))
        self.assertNotIn("login_captcha", self.client.session)

    def test_superadmin_can_change_username(self):
        """Superadmin can update the login username of any account or their own."""
        self.client.force_login(self.superadmin)

        # 1. Change accountant's username & designation
        edit_url = reverse("accounts:user_edit", kwargs={"pk": self.accountant.pk})
        res = self.client.post(edit_url, {
            "username": "acct_renamed",
            "display_name": "Accountant Renamed",
            "designation": "Head of Office Administration",
            "email": "acct_new@example.com",
            "role": Role.OFFICE_ADMIN,
            "is_active": True,
        })
        self.assertEqual(res.status_code, 302)
        self.accountant.refresh_from_db()
        self.assertEqual(self.accountant.username, "acct_renamed")
        self.assertEqual(self.accountant.designation, "Head of Office Administration")

        # 2. Change own superadmin username & designation
        self_edit_url = reverse("accounts:user_edit", kwargs={"pk": self.superadmin.pk})
        res2 = self.client.post(self_edit_url, {
            "username": "superadmin_new",
            "display_name": "Chief Superadmin",
            "designation": "Principal Superadmin",
            "email": "super_new@example.com",
        })
        self.assertEqual(res2.status_code, 302)
        self.superadmin.refresh_from_db()
        self.assertEqual(self.superadmin.username, "superadmin_new")
        self.assertEqual(self.superadmin.designation, "Principal Superadmin")

    def test_superadmin_can_create_user_with_designation(self):
        """Superadmin creates an Office Administration user with designation."""
        self.client.force_login(self.superadmin)
        res = self.client.post(reverse("accounts:user_create"), {
            "username": "officeadmin_new",
            "display_name": "New Admin Officer",
            "designation": "Executive Assistant",
            "email": "exec@example.com",
            "role": Role.OFFICE_ADMIN,
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
        })
        self.assertEqual(res.status_code, 302)
        new_user = User.objects.get(username="officeadmin_new")
        self.assertEqual(new_user.role, Role.OFFICE_ADMIN)
        self.assertEqual(new_user.designation, "Executive Assistant")
        self.assertTrue(new_user.is_office_admin)
        self.assertEqual(new_user.get_role_display(), "Office Administration")

    def test_inactivity_timeout_and_browser_close_session(self):
        """Verify 60-minute inactivity timeout and browser-close session invalidation."""
        # 1. Login sets browser-close cookie expiry
        login_res = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
        })
        self.assertRedirects(login_res, reverse("employees:dashboard"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

        # 2. Within timeout (active session works)
        active_res = self.client.get(reverse("employees:dashboard"))
        self.assertEqual(active_res.status_code, 200)

        # 3. Simulate 61 minutes of inactivity (> 3600 seconds)
        session = self.client.session
        session["_last_activity"] = int(timezone.now().timestamp()) - 3660
        session.save()

        # 4. Next request should automatically log out and redirect with ?timeout=1
        timeout_res = self.client.get(reverse("employees:dashboard"))
        self.assertEqual(timeout_res.status_code, 302)
        self.assertIn("timeout=1", timeout_res.url)


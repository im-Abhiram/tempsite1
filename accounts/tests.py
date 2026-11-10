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
        )
        self.accountant = User.objects.create_user(
            username="accountant1",
            password="StrongPassword123!",
            role=Role.ACCOUNTANT,
            display_name="Lead Accountant",
        )
        self.owner = User.objects.create_user(
            username="owner1",
            password="StrongPassword123!",
            role=Role.OWNER,
            display_name="Business Owner",
        )
        self.settings = CompanySettings.get()

    def test_user_role_properties(self):
        self.assertTrue(self.superadmin.is_superadmin)
        self.assertFalse(self.superadmin.is_accountant)
        self.assertFalse(self.superadmin.is_owner)

        self.assertTrue(self.accountant.is_accountant)
        self.assertFalse(self.accountant.is_superadmin)

        self.assertTrue(self.owner.is_owner)
        self.assertFalse(self.owner.is_superadmin)

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

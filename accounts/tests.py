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

        # 3. Solved CAPTCHA was consumed on failure; fetch a fresh challenge
        res2 = self.client.get(reverse("accounts:captcha_image"))
        new_captcha_code = self.client.session.get("login_captcha")

        # 4. Login attempt with fresh CORRECT answer succeeds
        ok_res = self.client.post(reverse("accounts:login"), {
            "username": "accountant1",
            "password": "StrongPassword123!",
            "captcha": new_captcha_code,
        })
        self.assertRedirects(ok_res, reverse("employees:dashboard"))
        self.assertNotIn("login_captcha", self.client.session)

    def test_open_redirect_prevention(self):
        """Next parameter with external or malformed redirect targets must be safely ignored."""
        malicious_urls = [
            "https://evil.com",
            "//evil.com",
            "/\\evil.com",
            "http://attacker.com/dashboard/",
        ]
        for url in malicious_urls:
            res = self.client.post(
                reverse("accounts:login") + f"?next={url}",
                {"username": "accountant1", "password": "StrongPassword123!"},
            )
            self.assertRedirects(res, reverse("employees:dashboard"))

    def test_clean_ip_and_middleware(self):
        """clean_ip must normalize valid IPs and reject malformed or malicious strings."""
        from accounts.middleware import clean_ip
        self.assertEqual(clean_ip("192.168.1.1"), "192.168.1.1")
        self.assertEqual(clean_ip("2001:db8::1"), "2001:db8::1")
        self.assertIsNone(clean_ip("<script>alert(1)</script>"))
        self.assertIsNone(clean_ip("invalid-ip-address"))
        self.assertIsNone(clean_ip(""))

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


class SecurityHeadersMiddlewareTests(TestCase):
    """
    Automated verification of defense-in-depth HTTP security headers and CSP nonces.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="sec_test_user",
            password="StrongPassword123!",
            role=Role.OFFICE_ADMIN,
            display_name="Security Tester",
        )

    def test_security_headers_present_on_response(self):
        """Verify presence and strict directives of all HTTP security headers."""
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

        # 1. Content-Security-Policy
        self.assertIn("Content-Security-Policy", response.headers)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'self'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("'nonce-", csp)
        # Ensure unsafe-inline and unsafe-eval are NOT in script-src
        script_part = csp.split("script-src")[1].split(";")[0]
        self.assertNotIn("'unsafe-inline'", script_part)
        self.assertNotIn("'unsafe-eval'", script_part)

        # 2. X-XSS-Protection: 0 (Modern standard)
        self.assertEqual(response.headers.get("X-XSS-Protection"), "0")

        # 3. Permissions-Policy
        self.assertIn("Permissions-Policy", response.headers)
        pp = response.headers["Permissions-Policy"]
        self.assertIn("camera=()", pp)
        self.assertIn("microphone=()", pp)
        self.assertIn("geolocation=()", pp)
        self.assertIn("payment=()", pp)
        self.assertIn("usb=()", pp)

        # 4. Cross-Origin Policies
        self.assertEqual(response.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(response.headers.get("Cross-Origin-Embedder-Policy"), "unsafe-none")
        self.assertEqual(response.headers.get("Cross-Origin-Opener-Policy"), "same-origin")

        # 5. Framing and Content Type Sniffing
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_nonce_is_unique_per_request(self):
        """Dynamic cryptographic nonces must differ across consecutive HTTP requests."""
        import re

        res1 = self.client.get(reverse("accounts:login"))
        res2 = self.client.get(reverse("accounts:login"))

        csp1 = res1.headers["Content-Security-Policy"]
        csp2 = res2.headers["Content-Security-Policy"]

        nonce1_match = re.search(r"'nonce-([^']+)'", csp1)
        nonce2_match = re.search(r"'nonce-([^']+)'", csp2)

        self.assertIsNotNone(nonce1_match)
        self.assertIsNotNone(nonce2_match)

        nonce1 = nonce1_match.group(1)
        nonce2 = nonce2_match.group(1)

        self.assertNotEqual(nonce1, nonce2)
        # Verify rendered template contains the exact matching nonce
        self.assertContains(res1, f'nonce="{nonce1}"')
        self.assertContains(res2, f'nonce="{nonce2}"')

    def test_csp_report_only_mode_toggle(self):
        """When CSP_REPORT_ONLY is True, Content-Security-Policy-Report-Only is emitted."""
        with self.settings(CSP_REPORT_ONLY=True):
            res = self.client.get(reverse("accounts:login"))
            self.assertIn("Content-Security-Policy-Report-Only", res.headers)
            self.assertNotIn("Content-Security-Policy", res.headers)

    def test_custom_coep_policy_setting(self):
        """COEP header respects the COEP_POLICY setting."""
        with self.settings(COEP_POLICY="require-corp"):
            res = self.client.get(reverse("accounts:login"))
            self.assertEqual(res.headers.get("Cross-Origin-Embedder-Policy"), "require-corp")



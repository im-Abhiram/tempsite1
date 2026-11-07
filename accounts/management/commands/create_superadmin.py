"""
Thamarayyath Employee Portal — Management Command: create_superadmin

Usage:
    python manage.py create_superadmin

Prompts for username and password securely.
The initial Superadmin account can ONLY be created via this command
(not through the web UI) to enforce physical access control.
"""

import getpass
from django.core.management.base import BaseCommand
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction


class Command(BaseCommand):
    help = "Create the initial Superadmin account for Thamarayyath Employee Portal."

    def handle(self, *args, **options):
        from accounts.models import CustomUser, Role

        self.stdout.write(self.style.WARNING(
            "\n=== Thamarayyath Employee Portal — Superadmin Setup ===\n"
            "This command creates the initial Superadmin account.\n"
            "Ensure you are running this on the secured workstation.\n"
        ))

        # Check if a Superadmin already exists
        existing = CustomUser.objects.filter(role=Role.SUPERADMIN).first()
        if existing:
            self.stdout.write(self.style.ERROR(
                f"A Superadmin account already exists: '{existing.username}'\n"
                "Use the web interface to manage accounts or reset the password."
            ))
            return

        # Prompt for username
        while True:
            username = input("Superadmin username: ").strip().lower()
            if not username:
                self.stdout.write(self.style.ERROR("Username cannot be empty."))
                continue
            if CustomUser.objects.filter(username=username).exists():
                self.stdout.write(self.style.ERROR(f"Username '{username}' already taken."))
                continue
            break

        # Prompt for display name
        display_name = input("Display name (press Enter to skip): ").strip()

        # Prompt for password with confirmation
        while True:
            password = getpass.getpass("Password (min 10 chars): ")
            if not password:
                self.stdout.write(self.style.ERROR("Password cannot be empty."))
                continue
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                self.stdout.write(self.style.ERROR("Passwords do not match. Try again."))
                continue

            # Validate against Django password validators
            try:
                validate_password(password)
            except ValidationError as e:
                self.stdout.write(self.style.ERROR("\n".join(e.messages)))
                continue
            break

        try:
            with transaction.atomic():
                user = CustomUser.objects.create_superadmin(
                    username=username,
                    password=password,
                    display_name=display_name or username.title(),
                    is_staff=True,
                )
                # Initialize company settings
                from accounts.models import CompanySettings
                CompanySettings.get()  # Creates with defaults if not exists

            self.stdout.write(self.style.SUCCESS(
                f"\n✔ Superadmin account '{user.username}' created successfully.\n"
                f"  You can now start the server and log in at /accounts/login/\n"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to create Superadmin: {e}"))

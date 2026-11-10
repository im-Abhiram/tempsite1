"""
Thamarayyath Employee Portal — Core & Backup Tests.
Tests live SQLite database backup consistency, storage calculation, and Superadmin-only restrictions.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import Role
from core.services import get_sqlite_backup_bytes, get_storage_usage

User = get_user_model()


class CoreBackupAndDiagnosticsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_superadmin(
            username="admin", password="StrongPassword123!"
        )
        self.accountant = User.objects.create_user(
            username="acct", password="StrongPassword123!", role=Role.ACCOUNTANT
        )
        self.owner = User.objects.create_user(
            username="owner", password="StrongPassword123!", role=Role.OWNER
        )

    def test_sqlite_binary_backup_generation(self):
        """Official SQLite backup API must return a non-empty SQLite file header (SQLite format 3)."""
        backup_bytes = get_sqlite_backup_bytes()
        self.assertGreater(len(backup_bytes), 100)
        # SQLite database files always begin with the magic header bytes: 'SQLite format 3\0'
        self.assertTrue(backup_bytes.startswith(b"SQLite format 3\x00"))

    def test_storage_usage_diagnostics(self):
        """Storage calculations must accurately report dictionary with bytes and display strings."""
        usage = get_storage_usage()
        self.assertIn("db_size_bytes", usage)
        self.assertIn("total_size_display", usage)
        self.assertIn("media_size_display", usage)

    def test_superadmin_can_download_database_backup(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(reverse("core:download_db_backup"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/x-sqlite3")
        self.assertTrue(response.content.startswith(b"SQLite format 3\x00"))

    def test_accountant_denied_database_backup(self):
        """Accountants must NEVER be able to download raw database snapshots."""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("core:download_db_backup"))
        self.assertEqual(response.status_code, 403)

    def test_owner_denied_database_backup(self):
        """Owners must NEVER be able to download database backups."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:download_db_backup"))
        self.assertEqual(response.status_code, 403)

    def test_image_and_document_compression(self):
        """Verify uploaded documents and photos are automatically compressed."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.compression import compress_uploaded_document, compress_profile_photo

        # 1. Create a large test image (2000 x 2000)
        img = Image.new("RGB", (2000, 2000), color=(180, 200, 220))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        raw_bytes = buf.getvalue()
        upload = SimpleUploadedFile("passport_scan.jpg", raw_bytes, content_type="image/jpeg")

        compressed = compress_uploaded_document(upload, max_dimension=1600, quality=75)
        self.assertLess(compressed.size, len(raw_bytes))

        # Check resized dimensions
        res_img = Image.open(compressed)
        self.assertLessEqual(max(res_img.size), 1600)

        # 2. Test profile photo compression (max 800px)
        upload_photo = SimpleUploadedFile("avatar.jpg", raw_bytes, content_type="image/jpeg")
        compressed_photo = compress_profile_photo(upload_photo)
        self.assertLess(compressed_photo.size, len(raw_bytes))
        photo_img = Image.open(compressed_photo)
        self.assertLessEqual(max(photo_img.size), 800)

        # 3. Test non-image file pass-through
        text_upload = SimpleUploadedFile("notes.txt", b"plain text content", content_type="text/plain")
        result = compress_uploaded_document(text_upload)
        self.assertEqual(result.read(), b"plain text content")



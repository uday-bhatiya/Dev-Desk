import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.models import Role, User

KEYS = ("DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_PASSWORD", "DJANGO_SUPERUSER_EMAIL")
STRONG = "Strong-admin-pass-2026"


class EnsureAdminTests(TestCase):
    def run_command(self, **env):
        out = StringIO()
        with patch.dict(os.environ):
            for key in KEYS:
                os.environ.pop(key, None)
            os.environ.update(env)
            call_command("ensure_admin", stdout=out)
        return out.getvalue()

    def test_creates_the_administrator(self):
        output = self.run_command(
            DJANGO_SUPERUSER_USERNAME="owner",
            DJANGO_SUPERUSER_PASSWORD=STRONG,
            DJANGO_SUPERUSER_EMAIL="owner@example.com",
        )
        user = User.objects.get(username="owner")
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.role, Role.ADMIN)
        self.assertTrue(user.check_password(STRONG))
        self.assertIn("Created", output)

    def test_second_run_changes_nothing(self):
        env = {"DJANGO_SUPERUSER_USERNAME": "owner", "DJANGO_SUPERUSER_PASSWORD": STRONG}
        self.run_command(**env)
        output = self.run_command(
            DJANGO_SUPERUSER_USERNAME="owner",
            DJANGO_SUPERUSER_PASSWORD="Another-pass-2026",
        )
        self.assertTrue(User.objects.get(username="owner").check_password(STRONG))
        self.assertIn("already exists", output)

    def test_skips_when_variables_are_missing(self):
        output = self.run_command()
        self.assertFalse(User.objects.exists())
        self.assertIn("skipping", output)

    def test_refuses_a_weak_password(self):
        with self.assertRaises(CommandError):
            self.run_command(
                DJANGO_SUPERUSER_USERNAME="owner", DJANGO_SUPERUSER_PASSWORD="123"
            )
        self.assertFalse(User.objects.exists())
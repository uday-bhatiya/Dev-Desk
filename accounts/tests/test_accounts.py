from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

OLD_PASSWORD = "Old-pass-12345"
NEW_PASSWORD = "Brand-new-pass-98765"


class UserRoleTests(TestCase):
    def test_default_role_is_employee(self):
        user = User.objects.create_user("emp", password=OLD_PASSWORD)
        self.assertEqual(user.role, Role.EMPLOYEE)
        self.assertTrue(user.is_employee)
        self.assertFalse(user.can_handle_tickets)

    def test_agent_and_admin_can_handle_tickets(self):
        agent = User.objects.create_user("a", password=OLD_PASSWORD, role=Role.AGENT)
        admin = User.objects.create_user("b", password=OLD_PASSWORD, role=Role.ADMIN)
        self.assertTrue(agent.can_handle_tickets)
        self.assertFalse(agent.is_it_admin)
        self.assertTrue(admin.can_handle_tickets)
        self.assertTrue(admin.is_it_admin)

    def test_superuser_always_gets_admin_role(self):
        root = User.objects.create_superuser("root", password=OLD_PASSWORD)
        self.assertEqual(root.role, Role.ADMIN)

    def test_database_rejects_invalid_role(self):
        user = User.objects.create_user("emp", password=OLD_PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(role="hacker")


class PasswordChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("emp", password=OLD_PASSWORD)

    def test_requires_login(self):
        url = reverse("password_change")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_successful_change(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": OLD_PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("ticket_list"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # The user stays logged in after the change.
        self.assertEqual(self.client.get(reverse("ticket_list")).status_code, 200)

    def test_wrong_old_password_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "not-my-password",
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))
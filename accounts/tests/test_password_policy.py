from django.test import TestCase
from django.urls import reverse

from accounts.models import User

OLD_PASSWORD = "Old-pass-12345"


class PasswordPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("emp", password=OLD_PASSWORD)

    def change_to(self, new_password):
        self.client.force_login(self.user)
        return self.client.post(
            reverse("password_change"),
            {
                "old_password": OLD_PASSWORD,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )

    def test_nine_characters_is_too_short(self):
        response = self.change_to("Abc-12345")  
        self.assertFormError(
            response.context["form"],
            "new_password2",
            "This password is too short. It must contain at least 10 characters.",
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_ten_or_more_characters_is_accepted(self):
        response = self.change_to("Abc-1234567-xyz")
        self.assertRedirects(response, reverse("ticket_list"))
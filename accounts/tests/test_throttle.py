from datetime import timedelta

from django.contrib.auth import authenticate
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import throttle
from accounts.models import LoginAttempt, User
from accounts.throttle import MAX_FAILURES_PER_ACCOUNT_AND_IP, MAX_FAILURES_PER_IP, WINDOW

PASSWORD = "Correct-pass-12345"
LOCKED_MESSAGE = "Too many failed login attempts"


class LoginThrottleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("emp", password=PASSWORD)
        cls.other = User.objects.create_user("emp2", password=PASSWORD)

    def attempt(self, username, password, **extra):
        return self.client.post(
            reverse("login"), {"username": username, "password": password}, **extra
        )

    def fail(self, username, times):
        for _ in range(times):
            self.attempt(username, "wrong-password")

    def test_failures_are_recorded_with_the_ip(self):
        self.fail("emp", 2)
        attempts = LoginAttempt.objects.filter(username="emp")
        self.assertEqual(attempts.count(), 2)
        self.assertEqual(attempts.first().ip_address, "127.0.0.1")

    def test_account_is_locked_after_too_many_failures(self):
        self.fail("emp", MAX_FAILURES_PER_ACCOUNT_AND_IP)
        response = self.attempt("emp", PASSWORD)  # even the correct password
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LOCKED_MESSAGE)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_below_the_limit_login_still_works(self):
        self.fail("emp", MAX_FAILURES_PER_ACCOUNT_AND_IP - 1)
        response = self.attempt("emp", PASSWORD)
        self.assertRedirects(response, reverse("ticket_list"))

    def test_other_accounts_are_not_locked(self):
        self.fail("emp", MAX_FAILURES_PER_ACCOUNT_AND_IP)
        response = self.attempt("emp2", PASSWORD)
        self.assertRedirects(response, reverse("ticket_list"))

    def test_backend_enforces_the_lock_for_any_login_path(self):
        # The admin login does not use our form, so the backend must block it.
        for _ in range(MAX_FAILURES_PER_ACCOUNT_AND_IP):
            LoginAttempt.objects.create(username="emp", ip_address="127.0.0.1")
        request = RequestFactory().post("/admin/login/")
        self.assertIsNone(authenticate(request, username="emp", password=PASSWORD))
        self.assertEqual(
            authenticate(request, username="emp2", password=PASSWORD), self.other
        )

    def test_lock_expires_after_the_window(self):
        for _ in range(MAX_FAILURES_PER_ACCOUNT_AND_IP):
            LoginAttempt.objects.create(username="emp", ip_address="127.0.0.1")
        LoginAttempt.objects.update(
            created_at=timezone.now() - WINDOW - timedelta(minutes=1)
        )
        response = self.attempt("emp", PASSWORD)
        self.assertRedirects(response, reverse("ticket_list"))

    def test_successful_login_clears_earlier_failures(self):
        self.fail("emp", 3)
        self.attempt("emp", PASSWORD)
        self.assertFalse(LoginAttempt.objects.filter(username="emp").exists())

    def test_username_is_case_insensitive_for_counting(self):
        self.fail("EMP", MAX_FAILURES_PER_ACCOUNT_AND_IP)
        response = self.attempt("emp", PASSWORD)
        self.assertContains(response, LOCKED_MESSAGE)

    def test_per_ip_limit_blocks_guessing_across_many_usernames(self):
        for number in range(MAX_FAILURES_PER_IP):
            LoginAttempt.objects.create(username=f"guess{number}", ip_address="127.0.0.1")
        response = self.attempt("emp", PASSWORD)
        self.assertContains(response, LOCKED_MESSAGE)

    def test_failures_from_another_ip_do_not_block_this_one(self):
        for _ in range(MAX_FAILURES_PER_ACCOUNT_AND_IP):
            LoginAttempt.objects.create(username="emp", ip_address="10.0.0.9")
        response = self.attempt("emp", PASSWORD)
        self.assertRedirects(response, reverse("ticket_list"))

    def test_old_rows_are_purged(self):
        old = LoginAttempt.objects.create(username="x", ip_address="1.1.1.1")
        LoginAttempt.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        throttle.record_failure("y", "2.2.2.2")
        self.assertFalse(LoginAttempt.objects.filter(pk=old.pk).exists())


class ClientIpTests(TestCase):
    def attempt(self, **extra):
        return self.client.post(
            reverse("login"), {"username": "emp", "password": "bad"}, **extra
        )

    def test_forwarded_header_is_ignored_by_default(self):
        self.attempt(HTTP_X_FORWARDED_FOR="9.9.9.9")
        self.assertEqual(LoginAttempt.objects.get().ip_address, "127.0.0.1")

    @override_settings(THROTTLE_TRUST_PROXY_HEADER=True)
    def test_forwarded_header_uses_the_last_entry_when_trusted(self):
        self.attempt(HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9")
        self.assertEqual(LoginAttempt.objects.get().ip_address, "9.9.9.9")

    @override_settings(THROTTLE_TRUST_PROXY_HEADER=True)
    def test_garbage_forwarded_value_does_not_crash(self):
        response = self.attempt(HTTP_X_FORWARDED_FOR="not-an-ip")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(LoginAttempt.objects.get().ip_address)
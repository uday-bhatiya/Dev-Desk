import re

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from tickets.models import Comment, Ticket

from .helpers import PASSWORD, make_category, make_ticket, make_user

INLINE_STYLE = re.compile(r"\sstyle\s*=", re.IGNORECASE)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)", re.IGNORECASE)


class SecurityHeaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        cls.agent = make_user("agent", Role.AGENT)
        cls.ticket = make_ticket(cls.employee, assignee=cls.agent)

    def test_csp_and_related_headers_on_app_pages(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_list"))
        policy = response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn("unsafe-inline", policy)
        self.assertIn("camera=()", response.headers["Permissions-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_login_page_has_the_csp_too(self):
        response = self.client.get(reverse("login"))
        self.assertIn("Content-Security-Policy", response.headers)

    def test_admin_is_exempt_from_the_csp(self):
        response = self.client.get("/admin/login/")
        self.assertNotIn("Content-Security-Policy", response.headers)

    def test_pages_contain_no_inline_styles_or_scripts(self):
        self.client.force_login(self.agent)
        urls = [
            reverse("ticket_list"),
            reverse("ticket_queue"),
            reverse("dashboard"),
            reverse("ticket_detail", args=[self.ticket.pk]),
            reverse("ticket_create"),
            reverse("password_change"),
        ]
        for url in urls:
            html = self.client.get(url).content.decode()
            self.assertIsNone(INLINE_STYLE.search(html), f"inline style on {url}")
            self.assertIsNone(INLINE_SCRIPT.search(html), f"inline script on {url}")
        self.client.logout()
        html = self.client.get(reverse("login")).content.decode()
        self.assertIsNone(INLINE_STYLE.search(html))
        self.assertIsNone(INLINE_SCRIPT.search(html))


class CookieTests(TestCase):
    def test_session_cookie_flags_and_lifetime(self):
        make_user("emp")
        self.client.post(reverse("login"), {"username": "emp", "password": PASSWORD})
        cookie = self.client.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(int(cookie["max-age"]), 12 * 60 * 60)


class InputLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        cls.category = make_category()

    def setUp(self):
        self.client.force_login(self.employee)

    def test_overlong_description_is_rejected(self):
        response = self.client.post(
            reverse("ticket_create"),
            {
                "title": "Printer problem",
                "category": self.category.pk,
                "description": "x" * 5001,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "description",
            "Please keep the description under 5000 characters.",
        )
        self.assertFalse(Ticket.objects.exists())

    def test_overlong_comment_is_rejected(self):
        ticket = make_ticket(self.employee)
        response = self.client.post(
            reverse("ticket_add_comment", args=[ticket.pk]),
            {"body": "x" * 2001},
            follow=True,
        )
        self.assertContains(response, "Please keep comments under 2000 characters.")
        self.assertFalse(Comment.objects.exists())

    def test_huge_request_body_is_refused(self):
        response = self.client.post(
            reverse("ticket_create"),
            {
                "title": "Printer problem",
                "category": self.category.pk,
                "description": "x" * 300_000,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Ticket.objects.exists())


class UiHookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        cls.agent = make_user("agent", Role.AGENT)
        cls.ticket = make_ticket(cls.employee, assignee=cls.agent)

    def test_base_layout_has_skip_link_script_and_favicon(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_list"))
        self.assertContains(response, 'class="skip-link"')
        self.assertContains(response, 'src="/static/js/app.js"')
        self.assertContains(response, "favicon.svg")

    def test_tables_have_captions_and_header_scopes(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_list"))
        self.assertContains(response, "<caption")
        self.assertContains(response, 'scope="col"')

    def test_closing_a_ticket_asks_for_confirmation(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse("ticket_detail", args=[self.ticket.pk]))
        self.assertContains(response, 'data-confirm-value="closed"')
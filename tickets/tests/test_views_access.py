from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from tickets.models import Comment, Ticket, TicketPriority, TicketStatus

from .helpers import PASSWORD, make_category, make_ticket, make_user


class AnonymousAccessTests(TestCase):
    def test_pages_redirect_anonymous_users_to_login(self):
        ticket = make_ticket(make_user("emp"))
        targets = [
            reverse("ticket_list"),
            reverse("ticket_create"),
            reverse("ticket_queue"),
            reverse("ticket_detail", args=[ticket.pk]),
        ]
        for url in targets:
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('login')}?next={url}")


class TicketVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp", Role.EMPLOYEE)
        cls.other_employee = make_user("emp2", Role.EMPLOYEE)
        cls.agent = make_user("agent", Role.AGENT)
        cls.mine = make_ticket(cls.employee, title="My own ticket")
        cls.foreign = make_ticket(cls.other_employee, title="Foreign ticket")

    def test_employee_list_contains_only_own_tickets(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_list"))
        self.assertContains(response, "My own ticket")
        self.assertNotContains(response, "Foreign ticket")

    def test_agent_list_contains_all_tickets(self):
        self.client.force_login(self.agent)
        response = self.client.get(reverse("ticket_list"))
        self.assertContains(response, "My own ticket")
        self.assertContains(response, "Foreign ticket")

    def test_employee_gets_404_for_foreign_ticket(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_detail", args=[self.foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

    def test_employee_can_open_own_ticket(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("ticket_detail", args=[self.mine.pk]))
        self.assertEqual(response.status_code, 200)

    def test_internal_notes_only_visible_to_staff(self):
        Comment.objects.create(
            ticket=self.mine, author=self.agent, body="Public reply text"
        )
        Comment.objects.create(
            ticket=self.mine,
            author=self.agent,
            body="SECRET internal note",
            is_internal=True,
        )
        url = reverse("ticket_detail", args=[self.mine.pk])

        self.client.force_login(self.employee)
        response = self.client.get(url)
        self.assertContains(response, "Public reply text")
        self.assertNotContains(response, "SECRET internal note")

        self.client.force_login(self.agent)
        response = self.client.get(url)
        self.assertContains(response, "SECRET internal note")


class AgentQueueTests(TestCase):
    def test_employee_gets_403(self):
        self.client.force_login(make_user("emp", Role.EMPLOYEE))
        response = self.client.get(reverse("ticket_queue"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")

    def test_agent_and_admin_can_open_queue(self):
        for username, role in (("agent", Role.AGENT), ("boss", Role.ADMIN)):
            self.client.force_login(make_user(username, role))
            response = self.client.get(reverse("ticket_queue"))
            self.assertEqual(response.status_code, 200)

    def test_queue_orders_by_priority_not_alphabetically(self):
        employee = make_user("emp")
        make_ticket(employee, title="Low one", priority=TicketPriority.LOW)
        make_ticket(employee, title="Urgent one", priority=TicketPriority.URGENT)
        make_ticket(employee, title="Medium one", priority=TicketPriority.MEDIUM)
        make_ticket(
            employee, title="Done one", priority=TicketPriority.URGENT,
            status=TicketStatus.CLOSED,
        )
        self.client.force_login(make_user("agent", Role.AGENT))
        response = self.client.get(reverse("ticket_queue"))
        titles = [t.title for t in response.context["unassigned"]]
        self.assertEqual(titles, ["Urgent one", "Medium one", "Low one"])


class TicketCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        cls.other = make_user("emp2")
        cls.agent = make_user("agent", Role.AGENT)
        cls.category = make_category()

    def setUp(self):
        self.client.force_login(self.employee)

    def test_create_sets_requester_and_ignores_forbidden_fields(self):
        data = {
            "title": "Cannot print",
            "category": self.category.pk,
            "description": "The printer shows an error message.",
            # A malicious user adds fields the form does not allow:
            "status": TicketStatus.CLOSED,
            "priority": TicketPriority.URGENT,
            "assignee": self.agent.pk,
            "requester": self.other.pk,
        }
        response = self.client.post(reverse("ticket_create"), data)
        ticket = Ticket.objects.get(title="Cannot print")
        self.assertRedirects(response, reverse("ticket_detail", args=[ticket.pk]))
        self.assertEqual(ticket.requester, self.employee)
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.priority, TicketPriority.MEDIUM)
        self.assertIsNone(ticket.assignee)

    def test_short_title_is_rejected(self):
        data = {
            "title": "abc",
            "category": self.category.pk,
            "description": "The printer shows an error message.",
        }
        response = self.client.post(reverse("ticket_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "title", "Please enter at least 5 characters."
        )
        self.assertFalse(Ticket.objects.exists())

    def test_html_in_ticket_is_escaped(self):
        ticket = make_ticket(self.employee, title="<script>alert(1)</script>")
        response = self.client.get(reverse("ticket_detail", args=[ticket.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")


class LoginLogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("emp")

    def test_login_with_valid_credentials(self):
        response = self.client.post(
            reverse("login"), {"username": "emp", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("ticket_list"))

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            reverse("login"), {"username": "emp", "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_via_post_ends_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
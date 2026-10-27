from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from tickets.models import Comment, TicketHistory, TicketPriority, TicketStatus

from .helpers import make_ticket, make_user


class WorkflowViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp", Role.EMPLOYEE)
        cls.other_employee = make_user("emp2", Role.EMPLOYEE)
        cls.agent = make_user("agent", Role.AGENT)
        cls.other_agent = make_user("agent2", Role.AGENT)
        cls.admin = make_user("boss", Role.ADMIN)

    def detail_url(self, ticket):
        return reverse("ticket_detail", args=[ticket.pk])

    def post(self, name, ticket, data, **kwargs):
        return self.client.post(reverse(name, args=[ticket.pk]), data, **kwargs)


class EndpointProtectionTests(WorkflowViewTestCase):
    def test_anonymous_post_redirects_to_login(self):
        ticket = make_ticket(self.employee)
        response = self.post("ticket_change_status", ticket, {"status": "in_progress"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_get_is_not_allowed(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.agent)
        for name in (
            "ticket_add_comment",
            "ticket_change_status",
            "ticket_change_priority",
            "ticket_assign",
        ):
            response = self.client.get(reverse(name, args=[ticket.pk]))
            self.assertEqual(response.status_code, 405, name)

    def test_employee_gets_403_on_staff_actions(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        self.client.force_login(self.employee)
        self.assertEqual(
            self.post("ticket_change_status", ticket, {"status": "in_progress"}).status_code,
            403,
        )
        self.assertEqual(
            self.post("ticket_change_priority", ticket, {"priority": "urgent"}).status_code,
            403,
        )
        self.assertEqual(
            self.post("ticket_assign", ticket, {"assignee": self.agent.pk}).status_code,
            403,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.priority, TicketPriority.MEDIUM)

    def test_agent_cannot_work_on_unassigned_or_foreign_ticket(self):
        unassigned = make_ticket(self.employee, title="Unassigned one")
        foreign = make_ticket(self.employee, assignee=self.other_agent, title="Foreign one")
        self.client.force_login(self.agent)
        for ticket in (unassigned, foreign):
            response = self.post("ticket_change_status", ticket, {"status": "in_progress"})
            self.assertEqual(response.status_code, 403)

    def test_employee_gets_404_for_foreign_ticket_actions(self):
        ticket = make_ticket(self.other_employee)
        self.client.force_login(self.employee)
        response = self.post("ticket_add_comment", ticket, {"body": "hello"})
        self.assertEqual(response.status_code, 404)


class StatusAndPriorityViewTests(WorkflowViewTestCase):
    def setUp(self):
        self.ticket = make_ticket(self.employee, assignee=self.agent)
        self.client.force_login(self.agent)

    def test_valid_status_change(self):
        response = self.post("ticket_change_status", self.ticket, {"status": "in_progress"})
        self.assertRedirects(response, self.detail_url(self.ticket))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)

    def test_history_is_shown_on_the_detail_page(self):
        self.post("ticket_change_status", self.ticket, {"status": "in_progress"})
        response = self.client.get(self.detail_url(self.ticket))
        self.assertContains(response, "changed status from Open to In progress")

    def test_disallowed_transition_is_rejected_by_the_form(self):
        response = self.post(
            "ticket_change_status", self.ticket, {"status": "closed"}, follow=True
        )
        self.assertContains(response, "Select a valid choice")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.OPEN)

    def test_priority_change(self):
        self.post("ticket_change_priority", self.ticket, {"priority": "high"})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.priority, TicketPriority.HIGH)
        self.assertEqual(TicketHistory.objects.filter(ticket=self.ticket).count(), 1)


class AssignViewTests(WorkflowViewTestCase):
    def test_agent_takes_unassigned_ticket(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.agent)
        self.post("ticket_assign", ticket, {"assignee": self.agent.pk})
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.agent)

    def test_agent_cannot_assign_to_another_agent_by_tampering(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.agent)
        response = self.post(
            "ticket_assign", ticket, {"assignee": self.other_agent.pk}, follow=True
        )
        self.assertContains(response, "Select a valid choice")
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assignee)

    def test_admin_reassigns_ticket(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        self.client.force_login(self.admin)
        self.post("ticket_assign", ticket, {"assignee": self.other_agent.pk})
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.other_agent)
        entry = TicketHistory.objects.get(ticket=ticket)
        self.assertEqual((entry.old_value, entry.new_value), ("agent", "agent2"))


class CommentViewTests(WorkflowViewTestCase):
    def test_employee_comment_ignores_tampered_internal_flag(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.employee)
        self.post("ticket_add_comment", ticket, {"body": "It happened again", "is_internal": "on"})
        comment = Comment.objects.get(ticket=ticket)
        self.assertFalse(comment.is_internal)

    def test_agent_internal_note_is_hidden_from_requester(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.agent)
        self.post("ticket_add_comment", ticket, {"body": "Hidden staff note", "is_internal": "on"})
        self.assertTrue(Comment.objects.get(ticket=ticket).is_internal)

        self.client.force_login(self.employee)
        response = self.client.get(self.detail_url(ticket))
        self.assertNotContains(response, "Hidden staff note")

    def test_empty_comment_is_rejected(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.employee)
        self.post("ticket_add_comment", ticket, {"body": "   "})
        self.assertEqual(Comment.objects.count(), 0)

    def test_employee_cannot_comment_on_closed_ticket(self):
        ticket = make_ticket(self.employee, status=TicketStatus.CLOSED)
        self.client.force_login(self.employee)
        response = self.post("ticket_add_comment", ticket, {"body": "reopen please"})
        self.assertEqual(response.status_code, 403)


class DetailPagePanelTests(WorkflowViewTestCase):
    def test_employee_sees_comment_box_but_no_action_panels(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.employee)
        response = self.client.get(self.detail_url(ticket))
        self.assertContains(response, "Add comment")
        self.assertNotContains(response, "Update status")
        self.assertNotContains(response, "Update priority")
        self.assertNotContains(response, "Assign ticket")

    def test_closed_ticket_hides_comment_box_for_employee(self):
        ticket = make_ticket(self.employee, status=TicketStatus.CLOSED)
        self.client.force_login(self.employee)
        response = self.client.get(self.detail_url(ticket))
        self.assertContains(response, "new comments are disabled")
        self.assertNotContains(response, "Add comment")

    def test_agent_on_unassigned_ticket_only_sees_assign_panel(self):
        ticket = make_ticket(self.employee)
        self.client.force_login(self.agent)
        response = self.client.get(self.detail_url(ticket))
        self.assertContains(response, "Assign ticket")
        self.assertNotContains(response, "Update status")

    def test_assigned_agent_sees_status_and_priority_panels(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        self.client.force_login(self.agent)
        response = self.client.get(self.detail_url(ticket))
        self.assertContains(response, "Update status")
        self.assertContains(response, "Update priority")
        self.assertNotContains(response, "Assign ticket")

    def test_admin_sees_all_panels(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        self.client.force_login(self.admin)
        response = self.client.get(self.detail_url(ticket))
        self.assertContains(response, "Assign ticket")
        self.assertContains(response, "Update status")
        self.assertContains(response, "Update priority")
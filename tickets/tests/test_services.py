from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.models import Role
from tickets import services
from tickets.models import (
    Comment,
    HistoryField,
    TicketHistory,
    TicketPriority,
    TicketStatus,
)

from .helpers import make_ticket, make_user


class BaseWorkflowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp", Role.EMPLOYEE)
        cls.other_employee = make_user("emp2", Role.EMPLOYEE)
        cls.agent = make_user("agent", Role.AGENT)
        cls.other_agent = make_user("agent2", Role.AGENT)
        cls.admin = make_user("boss", Role.ADMIN)

    def make_assigned_ticket(self, **extra):
        return make_ticket(self.employee, assignee=self.agent, **extra)


class StatusChangeTests(BaseWorkflowTest):
    def test_agent_moves_own_ticket_and_history_is_written(self):
        ticket = self.make_assigned_ticket()
        changed = services.change_status(self.agent, ticket, TicketStatus.IN_PROGRESS)
        ticket.refresh_from_db()
        self.assertTrue(changed)
        self.assertEqual(ticket.status, TicketStatus.IN_PROGRESS)
        entry = TicketHistory.objects.get(ticket=ticket)
        self.assertEqual(entry.field, HistoryField.STATUS)
        self.assertEqual(entry.old_value, "Open")
        self.assertEqual(entry.new_value, "In progress")
        self.assertEqual(entry.changed_by, self.agent)

    def test_resolved_at_is_set_and_cleared(self):
        ticket = self.make_assigned_ticket()
        services.change_status(self.agent, ticket, TicketStatus.RESOLVED)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.resolved_at)
        services.change_status(self.agent, ticket, TicketStatus.IN_PROGRESS) 
        ticket.refresh_from_db()
        self.assertIsNone(ticket.resolved_at)

    def test_same_status_is_a_noop(self):
        ticket = self.make_assigned_ticket()
        self.assertFalse(services.change_status(self.agent, ticket, TicketStatus.OPEN))
        self.assertEqual(TicketHistory.objects.count(), 0)

    def test_invalid_transition_is_rejected(self):
        ticket = self.make_assigned_ticket()  
        with self.assertRaises(services.WorkflowError):
            services.change_status(self.agent, ticket, TicketStatus.CLOSED)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(TicketHistory.objects.count(), 0)

    def test_unknown_status_is_rejected(self):
        ticket = self.make_assigned_ticket()
        with self.assertRaises(services.WorkflowError):
            services.change_status(self.agent, ticket, "bogus")

    def test_ticket_needs_an_assignee_before_work_starts(self):
        ticket = make_ticket(self.employee) 
        with self.assertRaises(services.WorkflowError):
            services.change_status(self.admin, ticket, TicketStatus.IN_PROGRESS)

    def test_other_agent_and_employee_are_denied(self):
        ticket = self.make_assigned_ticket()
        for user in (self.other_agent, self.employee):
            with self.assertRaises(PermissionDenied):
                services.change_status(user, ticket, TicketStatus.IN_PROGRESS)

    def test_closed_is_final_for_agents_but_admin_can_reopen(self):
        ticket = self.make_assigned_ticket(status=TicketStatus.CLOSED)
        with self.assertRaises(services.WorkflowError):
            services.change_status(self.agent, ticket, TicketStatus.OPEN)
        self.assertTrue(services.change_status(self.admin, ticket, TicketStatus.OPEN))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN)

    def test_failure_while_recording_history_rolls_back_the_change(self):
        ticket = self.make_assigned_ticket()
        with patch("tickets.services._record", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                services.change_status(self.agent, ticket, TicketStatus.IN_PROGRESS)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.OPEN) 
        self.assertEqual(TicketHistory.objects.count(), 0)


class PriorityChangeTests(BaseWorkflowTest):
    def test_assigned_agent_changes_priority_with_history(self):
        ticket = self.make_assigned_ticket()
        services.change_priority(self.agent, ticket, TicketPriority.HIGH)
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, TicketPriority.HIGH)
        entry = TicketHistory.objects.get(ticket=ticket)
        self.assertEqual((entry.old_value, entry.new_value), ("Medium", "High"))

    def test_unknown_priority_is_rejected(self):
        ticket = self.make_assigned_ticket()
        with self.assertRaises(services.WorkflowError):
            services.change_priority(self.agent, ticket, "critical")

    def test_other_agent_is_denied(self):
        ticket = self.make_assigned_ticket()
        with self.assertRaises(PermissionDenied):
            services.change_priority(self.other_agent, ticket, TicketPriority.HIGH)


class AssignmentTests(BaseWorkflowTest):
    def test_admin_assigns_and_reassigns_with_history(self):
        ticket = make_ticket(self.employee)
        services.assign_ticket(self.admin, ticket, self.agent)
        services.assign_ticket(self.admin, ticket, self.other_agent)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.other_agent)
        values = list(
            TicketHistory.objects.filter(ticket=ticket).values_list(
                "old_value", "new_value"
            )
        )
        self.assertEqual(values, [("", "agent"), ("agent", "agent2")])

    def test_agent_can_take_unassigned_ticket(self):
        ticket = make_ticket(self.employee)
        self.assertTrue(services.assign_ticket(self.agent, ticket, self.agent))
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.agent)

    def test_agent_cannot_assign_to_someone_else(self):
        ticket = make_ticket(self.employee)
        with self.assertRaises(PermissionDenied):
            services.assign_ticket(self.agent, ticket, self.other_agent)

    def test_agent_cannot_take_ticket_already_assigned_to_another_agent(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        with self.assertRaises(PermissionDenied):
            services.assign_ticket(self.other_agent, ticket, self.other_agent)

    def test_stale_object_cannot_bypass_the_rule(self):
        ticket_seen_by_second_agent = make_ticket(self.employee)
        services.assign_ticket(self.agent, ticket_seen_by_second_agent, self.agent)
        with self.assertRaises(PermissionDenied):
            services.assign_ticket(
                self.other_agent, ticket_seen_by_second_agent, self.other_agent
            )

    def test_employee_cannot_assign(self):
        ticket = make_ticket(self.employee)
        with self.assertRaises(PermissionDenied):
            services.assign_ticket(self.employee, ticket, self.agent)

    def test_assigning_same_person_is_a_noop(self):
        ticket = make_ticket(self.employee, assignee=self.agent)
        self.assertFalse(services.assign_ticket(self.admin, ticket, self.agent))
        self.assertEqual(TicketHistory.objects.count(), 0)


class CommentTests(BaseWorkflowTest):
    def test_requester_can_comment_on_own_ticket(self):
        ticket = make_ticket(self.employee)
        comment = services.add_comment(self.employee, ticket, "Still broken")
        self.assertEqual(comment.author, self.employee)
        self.assertFalse(comment.is_internal)

    def test_comment_updates_last_updated(self):
        ticket = make_ticket(self.employee)
        before = ticket.updated_at
        services.add_comment(self.employee, ticket, "Any news?")
        ticket.refresh_from_db()
        self.assertGreater(ticket.updated_at, before)

    def test_employee_cannot_post_internal_note(self):
        ticket = make_ticket(self.employee)
        with self.assertRaises(PermissionDenied):
            services.add_comment(self.employee, ticket, "sneaky", is_internal=True)
        self.assertEqual(Comment.objects.count(), 0)

    def test_employee_cannot_comment_on_someone_elses_ticket(self):
        ticket = make_ticket(self.employee)
        with self.assertRaises(PermissionDenied):
            services.add_comment(self.other_employee, ticket, "hello")

    def test_employee_cannot_comment_on_closed_ticket(self):
        ticket = make_ticket(self.employee, status=TicketStatus.CLOSED)
        with self.assertRaises(PermissionDenied):
            services.add_comment(self.employee, ticket, "one more thing")

    def test_agent_can_post_internal_note(self):
        ticket = make_ticket(self.employee)
        comment = services.add_comment(self.agent, ticket, "note", is_internal=True)
        self.assertTrue(comment.is_internal)
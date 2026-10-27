from django.test import TestCase

from accounts.models import Role
from tickets import permissions
from tickets.models import Comment, TicketStatus

from .helpers import make_ticket, make_user


class PermissionRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp", Role.EMPLOYEE)
        cls.other_employee = make_user("emp2", Role.EMPLOYEE)
        cls.agent = make_user("agent", Role.AGENT)
        cls.other_agent = make_user("agent2", Role.AGENT)
        cls.admin = make_user("boss", Role.ADMIN)

        cls.unassigned = make_ticket(cls.employee, title="Unassigned ticket")
        cls.assigned = make_ticket(
            cls.employee, assignee=cls.agent, title="Assigned ticket"
        )

    # ---- visibility ----

    def test_employee_sees_only_own_tickets(self):
        foreign = make_ticket(self.other_employee, title="Someone else's")
        visible = permissions.visible_tickets(self.employee)
        self.assertIn(self.unassigned, visible)
        self.assertNotIn(foreign, visible)

    def test_agent_and_admin_see_all_tickets(self):
        foreign = make_ticket(self.other_employee, title="Someone else's")
        for user in (self.agent, self.admin):
            self.assertIn(foreign, permissions.visible_tickets(user))

    def test_can_view_ticket(self):
        self.assertTrue(permissions.can_view_ticket(self.employee, self.unassigned))
        self.assertFalse(
            permissions.can_view_ticket(self.other_employee, self.unassigned)
        )
        self.assertTrue(permissions.can_view_ticket(self.agent, self.unassigned))

    def test_internal_notes_hidden_from_employees(self):
        Comment.objects.create(
            ticket=self.assigned, author=self.agent, body="public reply"
        )
        Comment.objects.create(
            ticket=self.assigned, author=self.agent, body="private", is_internal=True
        )
        employee_view = permissions.visible_comments(self.employee, self.assigned)
        agent_view = permissions.visible_comments(self.agent, self.assigned)
        self.assertEqual(employee_view.count(), 1)
        self.assertEqual(agent_view.count(), 2)

    # ---- commenting ----

    def test_employee_cannot_comment_on_closed_ticket(self):
        closed = make_ticket(self.employee, title="Closed", status=TicketStatus.CLOSED)
        self.assertFalse(permissions.can_comment(self.employee, closed))
        self.assertTrue(permissions.can_comment(self.agent, closed))

    def test_employee_cannot_comment_on_foreign_ticket(self):
        self.assertFalse(permissions.can_comment(self.other_employee, self.unassigned))

    def test_only_staff_can_post_internal_notes(self):
        self.assertFalse(permissions.can_post_internal_note(self.employee))
        self.assertTrue(permissions.can_post_internal_note(self.agent))
        self.assertTrue(permissions.can_post_internal_note(self.admin))

    # ---- status and priority ----

    def test_status_and_priority_rules(self):
        for check in (permissions.can_change_status, permissions.can_change_priority):
            self.assertTrue(check(self.admin, self.unassigned))
            self.assertTrue(check(self.agent, self.assigned))          # their own
            self.assertFalse(check(self.other_agent, self.assigned))   # someone else's
            self.assertFalse(check(self.agent, self.unassigned))       # not theirs yet
            self.assertFalse(check(self.employee, self.assigned))      # employees never

    # ---- assignment ----

    def test_admin_can_assign_to_any_active_staff_member(self):
        inactive = make_user("gone", Role.AGENT, is_active=False)
        users = permissions.assignable_users(self.admin, self.unassigned)
        self.assertIn(self.agent, users)
        self.assertIn(self.other_agent, users)
        self.assertIn(self.admin, users)
        self.assertNotIn(self.employee, users)
        self.assertNotIn(inactive, users)

    def test_agent_can_only_take_unassigned_ticket_for_themselves(self):
        users = permissions.assignable_users(self.agent, self.unassigned)
        self.assertEqual(list(users), [self.agent])
        self.assertTrue(permissions.can_assign(self.agent, self.unassigned))

    def test_agent_cannot_touch_ticket_assigned_to_another_agent(self):
        self.assertFalse(permissions.can_assign(self.other_agent, self.assigned))

    def test_employee_cannot_assign(self):
        self.assertFalse(permissions.can_assign(self.employee, self.unassigned))
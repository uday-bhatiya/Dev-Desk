from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.models import F
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from tickets.dashboard import TREND_DAYS, build_dashboard, humanize_duration
from tickets.models import Ticket, TicketPriority, TicketStatus

from .helpers import make_category, make_ticket, make_user


class HumanizeDurationTests(TestCase):
    def test_formats(self):
        self.assertEqual(humanize_duration(None), "No data yet")
        self.assertEqual(humanize_duration(timedelta(minutes=5)), "5m")
        self.assertEqual(humanize_duration(timedelta(hours=3, minutes=20)), "3h 20m")
        self.assertEqual(humanize_duration(timedelta(days=2, hours=5)), "2d 5h")


class DashboardAccessTests(TestCase):
    def test_anonymous_is_redirected(self):
        url = reverse("dashboard")
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_employee_gets_403(self):
        self.client.force_login(make_user("emp"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_agent_and_admin_can_open_it(self):
        for username, role in (("agent", Role.AGENT), ("boss", Role.ADMIN)):
            self.client.force_login(make_user(username, role))
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Active tickets")


class DashboardNumbersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now()
        cls.employee = make_user("emp")
        cls.agent = make_user("agent", Role.AGENT)

        make_ticket(cls.employee, title="t1", priority=TicketPriority.URGENT)
        make_ticket(cls.employee, title="t2", priority=TicketPriority.LOW)
        make_ticket(
            cls.employee, assignee=cls.agent, title="t3",
            priority=TicketPriority.HIGH, status=TicketStatus.IN_PROGRESS,
        )
        resolved = make_ticket(
            cls.employee, assignee=cls.agent, title="t4", status=TicketStatus.RESOLVED
        )
        closed = make_ticket(
            cls.employee, assignee=cls.agent, title="t5", status=TicketStatus.CLOSED
        )
        
        for ticket, days_ago, hours_to_resolve in ((resolved, 2, 4), (closed, 3, 8)):
            created = cls.now - timedelta(days=days_ago)
            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created,
                resolved_at=created + timedelta(hours=hours_to_resolve),
            )

    def data(self):
        return build_dashboard(self.agent, now=self.now)

    def test_headline_numbers(self):
        stats = self.data()["stats"]
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["active"], 3)
        self.assertEqual(stats["unassigned_active"], 2)
        self.assertEqual(stats["urgent_active"], 1)
        self.assertEqual(stats["resolved_last_7_days"], 2)
        self.assertEqual(stats["avg_resolution_display"], "6h 0m")

    def test_by_status(self):
        totals = [row["total"] for row in self.data()["by_status"]]
        self.assertEqual(totals, [2, 1, 1, 1])  

    def test_by_priority_counts_active_tickets_urgent_first(self):
        totals = [row["total"] for row in self.data()["by_priority"]]
        self.assertEqual(totals, [1, 1, 0, 1]) 
    def test_category_rows(self):
        rows = self.data()["categories"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["total"], rows[0]["active"]), (5, 3))

    def test_agent_workload(self):
        workload = {user.pk: user for user in self.data()["workload"]}
        agent = workload[self.agent.pk]
        self.assertEqual(agent.active_count, 1)
        self.assertEqual(agent.resolved_count, 2)

    def test_trend_covers_every_day_and_counts_every_ticket(self):
        trend = self.data()["trend"]
        self.assertEqual(len(trend), TREND_DAYS)
        self.assertEqual(sum(day["total"] for day in trend), 5)

    def test_oldest_unassigned_is_ordered(self):
        titles = [t.title for t in self.data()["oldest_unassigned"]]
        self.assertEqual(titles, ["t1", "t2"])


class DashboardEdgeCaseTests(TestCase):
    def test_empty_database_does_not_crash(self):
        agent = make_user("agent", Role.AGENT)
        data = build_dashboard(agent)
        self.assertEqual(data["stats"]["total"], 0)
        self.assertEqual(data["stats"]["avg_resolution_display"], "No data yet")
        self.assertTrue(all(row["percent"] == 0 for row in data["by_status"]))
        self.assertTrue(all(day["percent"] == 0 for day in data["trend"]))

    def test_query_count_does_not_grow_with_rows(self):
        employee = make_user("emp")
        agent = make_user("agent", Role.AGENT)
        self.client.force_login(agent)
        for number in range(2):
            make_ticket(employee, assignee=agent, title=f"Small {number}")

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.client.get(reverse("dashboard"))
            return len(queries)

        few = count()
        for number in range(15):
            make_ticket(
                make_user(f"user{number}"),
                title=f"More {number}",
                category=make_category(f"Category {number}"),
            )
        self.assertEqual(few, count())


@override_settings(DEBUG=True)
class SeedCommandTests(TestCase):
    def run_command(self, *args):
        call_command(*args, stdout=StringIO())

    def test_seed_bulk_creates_backdated_tickets_and_is_repeatable(self):
        self.run_command("seed_demo")
        before = Ticket.objects.count()

        self.run_command("seed_bulk", "--count", "30")
        self.assertEqual(Ticket.objects.count() - before, 30)

        self.run_command("seed_bulk", "--count", "30")
        self.assertEqual(Ticket.objects.count() - before, 30)  

        old_enough = timezone.now() - timedelta(days=20)
        self.assertTrue(Ticket.objects.filter(created_at__lt=old_enough).exists())
        self.assertFalse(Ticket.objects.filter(resolved_at__lt=F("created_at")).exists())

    def test_seed_bulk_needs_demo_data_first(self):
        with self.assertRaises(CommandError):
            self.run_command("seed_bulk")

    def test_seed_commands_refuse_to_run_outside_debug(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self.run_command("seed_demo")
            with self.assertRaises(CommandError):
                self.run_command("seed_bulk")
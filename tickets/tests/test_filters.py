from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Role
from tickets.models import TicketPriority, TicketStatus
from tickets.views import PAGE_SIZE

from .helpers import make_category, make_ticket, make_user


def titles(response):
    return [ticket.title for ticket in response.context["page_obj"]]


class SearchAndFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        cls.other = make_user("emp2")
        cls.agent = make_user("agent", Role.AGENT)
        cls.hardware = make_category("Hardware")
        cls.network = make_category("Network")

        cls.vpn = make_ticket(
            cls.employee,
            title="VPN keeps dropping",
            category=cls.network,
            priority=TicketPriority.HIGH,
            description="Connection drops every ten minutes.",
        )
        cls.laptop = make_ticket(
            cls.employee,
            assignee=cls.agent,
            title="Laptop will not boot",
            category=cls.hardware,
            status=TicketStatus.IN_PROGRESS,
            description="Black screen after the logo.",
        )
        cls.secret = make_ticket(
            cls.other,
            title="Secret salary spreadsheet access",
            category=cls.hardware,
        )

    def get(self, user, **params):
        self.client.force_login(user)
        return self.client.get(reverse("ticket_list"), params)

    # ---- search ----

    def test_search_matches_title_case_insensitively(self):
        self.assertEqual(titles(self.get(self.employee, q="vpn")), ["VPN keeps dropping"])

    def test_search_matches_description(self):
        response = self.get(self.employee, q="black screen")
        self.assertEqual(titles(response), ["Laptop will not boot"])

    def test_all_words_must_match(self):
        self.assertEqual(titles(self.get(self.employee, q="vpn laptop")), [])

    def test_search_by_ticket_number(self):
        for query in (f"#{self.laptop.pk}", str(self.laptop.pk)):
            response = self.get(self.employee, q=query)
            self.assertEqual(titles(response), ["Laptop will not boot"], query)

    def test_search_cannot_reveal_other_users_tickets(self):
        self.assertEqual(titles(self.get(self.employee, q="salary")), [])
        self.assertEqual(
            titles(self.get(self.agent, q="salary")),
            ["Secret salary spreadsheet access"],
        )

    def test_staff_can_search_by_requester_but_employees_cannot(self):
        self.assertEqual(
            titles(self.get(self.agent, q="emp2")),
            ["Secret salary spreadsheet access"],
        )
        self.assertEqual(titles(self.get(self.employee, q="emp")), [])

    def test_huge_number_does_not_crash(self):
        response = self.get(self.employee, q="9" * 30)
        self.assertEqual(response.status_code, 200)

    # ---- filters ----

    def test_status_priority_and_category_filters(self):
        self.assertEqual(
            titles(self.get(self.employee, status="in_progress")),
            ["Laptop will not boot"],
        )
        self.assertEqual(
            titles(self.get(self.employee, priority="high")), ["VPN keeps dropping"]
        )
        self.assertEqual(
            titles(self.get(self.employee, category=self.network.pk)),
            ["VPN keeps dropping"],
        )

    def test_assignment_filter_for_staff(self):
        self.assertEqual(
            titles(self.get(self.agent, assignment="me")), ["Laptop will not boot"]
        )
        unassigned = set(titles(self.get(self.agent, assignment="unassigned")))
        self.assertEqual(
            unassigned, {"VPN keeps dropping", "Secret salary spreadsheet access"}
        )

    def test_employee_cannot_use_assignment_filter(self):
        response = self.get(self.employee, assignment="me")
        self.assertEqual(
            set(titles(response)), {"VPN keeps dropping", "Laptop will not boot"}
        )

    def test_invalid_filter_is_ignored_with_a_warning(self):
        response = self.get(self.employee, status="bogus")
        self.assertContains(response, "Some filters were not valid")
        self.assertEqual(len(titles(response)), 2)

    # ---- sorting ----

    def test_sorting(self):
        self.assertEqual(
            titles(self.get(self.employee, sort="priority")),
            ["VPN keeps dropping", "Laptop will not boot"],  # high before medium
        )
        self.assertEqual(
            titles(self.get(self.employee, sort="oldest")),
            ["VPN keeps dropping", "Laptop will not boot"],
        )
        self.assertEqual(
            titles(self.get(self.employee, sort="newest")),
            ["Laptop will not boot", "VPN keeps dropping"],
        )


class PaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user("emp")
        for number in range(25):
            make_ticket(cls.employee, title=f"Bulk ticket {number:02d}")

    def setUp(self):
        self.client.force_login(self.employee)

    def get_page(self, **params):
        return self.client.get(reverse("ticket_list"), params)

    def test_page_sizes(self):
        self.assertEqual(len(self.get_page().context["page_obj"]), PAGE_SIZE)
        self.assertEqual(len(self.get_page(page=3).context["page_obj"]), 5)

    def test_no_ticket_is_repeated_or_skipped(self):
        seen = []
        for page in (1, 2, 3):
            seen += [t.pk for t in self.get_page(page=page).context["page_obj"]]
        self.assertEqual(len(seen), 25)
        self.assertEqual(len(set(seen)), 25)

    def test_bad_page_numbers_fall_back_safely(self):
        self.assertEqual(self.get_page(page=999).context["page_obj"].number, 3)
        self.assertEqual(self.get_page(page="abc").context["page_obj"].number, 1)

    def test_pagination_links_keep_the_filters(self):
        response = self.get_page(q="Bulk")
        self.assertContains(response, "q=Bulk&amp;page=2")


class QueryCountTests(TestCase):
    def count_queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("ticket_list"))
        return len(queries)

    def test_ticket_list_query_count_does_not_grow_with_rows(self):
        employee = make_user("emp")
        agent = make_user("agent", Role.AGENT)
        self.client.force_login(agent)
        for number in range(2):
            make_ticket(employee, assignee=agent, title=f"Small {number}")
        few = self.count_queries()

        for number in range(6):
            make_ticket(
                make_user(f"user{number}"),
                assignee=agent,
                title=f"More {number}",
                category=make_category(f"Category {number}"),
            )
        many = self.count_queries()

        self.assertEqual(few, many)  
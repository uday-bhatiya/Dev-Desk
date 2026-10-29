from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role
from tickets.models import Category, Comment, Ticket, TicketPriority, TicketStatus

User = get_user_model()

CATEGORIES = [
    ("Hardware", "Laptops, monitors and peripherals"),
    ("Software", "Installation and application problems"),
    ("Network", "VPN, Wi-Fi and connectivity"),
    ("Access & Accounts", "Passwords and permissions"),
    ("Email & Collaboration", "Mail, calendar and chat tools"),
]

DEMO_USERS = [ 
    ("employee1", "Asha", "Patel", Role.EMPLOYEE),
    ("employee2", "Rohan", "Mehta", Role.EMPLOYEE),
    ("agent1", "Neha", "Shah", Role.AGENT),
    ("agent2", "Karan", "Desai", Role.AGENT),
    ("admin1", "Priya", "Joshi", Role.ADMIN),
]

# (title, description, category, priority, status, requester, assignee)
TICKETS = [
    ("Laptop will not boot", "Screen stays black after the logo appears.",
     "Hardware", TicketPriority.HIGH, TicketStatus.IN_PROGRESS, "employee1", "agent1"),
    ("VPN disconnects every few minutes", "Drops while working from home.",
     "Network", TicketPriority.HIGH, TicketStatus.OPEN, "employee2", None),
    ("Access to shared finance folder", "Need read access for quarter-end reports.",
     "Access & Accounts", TicketPriority.MEDIUM, TicketStatus.OPEN, "employee1", None),
    ("Outlook keeps asking for password", "Prompt appears after every restart.",
     "Email & Collaboration", TicketPriority.MEDIUM, TicketStatus.RESOLVED, "employee2", "agent2"),
    ("Install Visual Studio Code", "Needed for the new project.",
     "Software", TicketPriority.LOW, TicketStatus.CLOSED, "employee1", "agent1"),
    ("Wi-Fi very slow on floor 3", "Speed tests show under 2 Mbps.",
     "Network", TicketPriority.URGENT, TicketStatus.IN_PROGRESS, "employee2", "agent2"),
    ("Monitor flickers", "Flickers when the laptop is docked.",
     "Hardware", TicketPriority.LOW, TicketStatus.OPEN, "employee1", None),
    ("Cannot join video calls", "Camera and microphone not detected.",
     "Software", TicketPriority.HIGH, TicketStatus.OPEN, "employee2", "agent1"),
    ("Password reset not working", "Reset email never arrives.",
     "Access & Accounts", TicketPriority.URGENT, TicketStatus.RESOLVED, "employee1", "agent1"),
    ("Shared calendar not syncing", "Team calendar shows old events.",
     "Email & Collaboration", TicketPriority.LOW, TicketStatus.CLOSED, "employee2", "agent2"),
]


class Command(BaseCommand):
    help = "Create demo users, categories, tickets and comments (development only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="DevDesk-demo-123!",
            help="Password for the demo users (development only).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not (settings.DEBUG or getattr(settings, "DEMO_MODE", False)):
            raise CommandError(
                "seed_demo only runs when DJANGO_DEBUG=True or DJANGO_DEMO_MODE=True."
            )

        users = {}
        for username, first, last, role in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@devdesk.local",
                    "role": role,
                },
            )
            if created:
                user.set_password(options["password"])
                user.save()
            users[username] = user

        categories = {}
        for name, description in CATEGORIES:
            category, _ = Category.objects.get_or_create(
                name=name, defaults={"description": description}
            )
            categories[name] = category

        new_tickets = 0
        for title, description, cat, priority, status, requester, assignee in TICKETS:
            ticket, created = Ticket.objects.get_or_create(
                title=title,
                requester=users[requester],
                defaults={
                    "description": description,
                    "category": categories[cat],
                    "priority": priority,
                    "status": status,
                    "assignee": users[assignee] if assignee else None,
                },
            )
            if created:
                new_tickets += 1
                if assignee:
                    Comment.objects.create(
                        ticket=ticket,
                        author=users[assignee],
                        body="Thanks for reporting this. I am looking into it.",
                    )
                    Comment.objects.create(
                        ticket=ticket,
                        author=users[assignee],
                        body="Checked the logs; will escalate if it continues.",
                        is_internal=True,
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {len(users)} users, {len(categories)} categories, "
                f"{new_tickets} new tickets."
            )
        )
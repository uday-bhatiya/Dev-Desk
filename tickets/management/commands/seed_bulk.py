import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from tickets.models import Category, Ticket, TicketPriority, TicketStatus

ISSUES = [
    ("Laptop battery drains too quickly", "Hardware"),
    ("Docking station is not detected", "Hardware"),
    ("Keyboard keys are unresponsive", "Hardware"),
    ("Cannot install required software", "Software"),
    ("Application crashes on startup", "Software"),
    ("License expired for design tool", "Software"),
    ("VPN connection keeps timing out", "Network"),
    ("Wi-Fi unavailable in meeting room", "Network"),
    ("Shared drive is not accessible", "Access & Accounts"),
    ("Account locked after password change", "Access & Accounts"),
    ("Need access to the reporting dashboard", "Access & Accounts"),
    ("Emails are stuck in the outbox", "Email & Collaboration"),
    ("Calendar invites are not arriving", "Email & Collaboration"),
]


def status_weights(age_days):
    if age_days >= 20:
        return [60, 25, 10, 5]
    if age_days >= 7:
        return [30, 35, 20, 15]
    return [5, 15, 35, 45]


class Command(BaseCommand):
    help = "Create many backdated sample tickets (development only). Run seed_demo first."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=60)

    @transaction.atomic
    def handle(self, *args, **options):
        if not (settings.DEBUG or getattr(settings, "DEMO_MODE", False)):
            raise CommandError(
                "seed_bulk only runs when DJANGO_DEBUG=True or DJANGO_DEMO_MODE=True."
            )

        employees = list(
            User.objects.filter(role=Role.EMPLOYEE, is_active=True).order_by("username")
        )
        staff = list(
            User.objects.filter(
                role__in=[Role.AGENT, Role.ADMIN], is_active=True
            ).order_by("username")
        )
        categories = {category.name: category for category in Category.objects.all()}
        missing = {name for _, name in ISSUES} - set(categories)
        if not employees or not staff or missing:
            raise CommandError("Run `python manage.py seed_demo` first.")

        rng = random.Random(42) 
        now = timezone.now()
        created_count = 0

        for number in range(1, options["count"] + 1):
            issue, category_name = rng.choice(ISSUES)
            requester = rng.choice(employees)
            priority = rng.choices(
                [
                    TicketPriority.LOW,
                    TicketPriority.MEDIUM,
                    TicketPriority.HIGH,
                    TicketPriority.URGENT,
                ],
                weights=[3, 5, 3, 1],
            )[0]
            age_days = rng.randint(0, 59)
            created_at = now - timedelta(
                days=age_days, hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
            )
            status = rng.choices(
                [
                    TicketStatus.CLOSED,
                    TicketStatus.RESOLVED,
                    TicketStatus.IN_PROGRESS,
                    TicketStatus.OPEN,
                ],
                weights=status_weights(age_days),
            )[0]
            assignee = rng.choice(staff)
            leave_unassigned = rng.random() < 0.7
            resolution_time = timedelta(hours=rng.randint(1, 96))
            title = f"{issue} [{number:03d}]"

            if status == TicketStatus.OPEN and leave_unassigned:
                assignee = None
            if Ticket.objects.filter(title=title, requester=requester).exists():
                continue

            ticket = Ticket.objects.create(
                title=title,
                description=f"Sample ticket generated for demo data. Issue: {issue}.",
                category=categories[category_name],
                requester=requester,
                assignee=assignee,
                priority=priority,
                status=status,
            )

            resolved_at = None
            if ticket.is_finished:
                resolved_at = min(created_at + resolution_time, now)
            updated_at = resolved_at or min(created_at + resolution_time // 2, now)

            Ticket.objects.filter(pk=ticket.pk).update(
                created_at=created_at, updated_at=updated_at, resolved_at=resolved_at
            )
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} sample tickets.")
        )
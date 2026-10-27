from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import Role, User

from . import permissions
from .filters import ACTIVE_STATUSES
from .models import TicketPriority, TicketStatus

TREND_DAYS = 14


def humanize_duration(delta):
    """Format a timedelta as '2d 5h', '3h 20m' or '5m'."""
    if delta is None:
        return "No data yet"
    minutes = int(delta.total_seconds() // 60)
    days, remainder = divmod(minutes, 60 * 24)
    hours, mins = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def _percent(value, whole):
    return round(value * 100 / whole) if whole else 0


def build_dashboard(user, now=None):
    """Return all dashboard data. Everything comes from database queries."""
    now = now or timezone.now()
    tickets = permissions.visible_tickets(user)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    stats = tickets.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status__in=ACTIVE_STATUSES)),
        unassigned_active=Count(
            "id", filter=Q(status__in=ACTIVE_STATUSES, assignee__isnull=True)
        ),
        urgent_active=Count(
            "id",
            filter=Q(status__in=ACTIVE_STATUSES, priority=TicketPriority.URGENT),
        ),
        resolved_last_7_days=Count("id", filter=Q(resolved_at__gte=week_ago)),
        avg_resolution=Avg(
            ExpressionWrapper(
                F("resolved_at") - F("created_at"), output_field=DurationField()
            ),
            filter=Q(resolved_at__gte=month_ago),
        ),
    )
    stats["avg_resolution_display"] = humanize_duration(stats["avg_resolution"])

    status_counts = {
        row["status"]: row["total"]
        for row in tickets.values("status").annotate(total=Count("id")).order_by()
    }
    by_status = [
        {
            "label": status.label,
            "total": status_counts.get(status.value, 0),
            "percent": _percent(status_counts.get(status.value, 0), stats["total"]),
        }
        for status in TicketStatus
    ]

    priority_counts = {
        row["priority"]: row["total"]
        for row in tickets.filter(status__in=ACTIVE_STATUSES)
        .values("priority")
        .annotate(total=Count("id"))
        .order_by()
    }
    by_priority = [
        {
            "label": priority.label,
            "total": priority_counts.get(priority.value, 0),
            "percent": _percent(priority_counts.get(priority.value, 0), stats["active"]),
        }
        for priority in reversed(list(TicketPriority))
    ]

    category_rows = (
        tickets.values("category__name")
        .annotate(
            total=Count("id"),
            active=Count("id", filter=Q(status__in=ACTIVE_STATUSES)),
        )
        .order_by("-active", "category__name")
    )
    categories = [
        {"name": row["category__name"], "total": row["total"], "active": row["active"]}
        for row in category_rows
    ]
    
    workload = (
        User.objects.filter(is_active=True, role__in=[Role.AGENT, Role.ADMIN])
        .annotate(
            active_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__status__in=ACTIVE_STATUSES),
            ),
            resolved_count=Count(
                "assigned_tickets",
                filter=Q(assigned_tickets__resolved_at__gte=month_ago),
            ),
        )
        .order_by("-active_count", "username")
    )

    today = timezone.localdate(now)
    first_day = today - timedelta(days=TREND_DAYS - 1)
    per_day = {
        row["day"]: row["total"]
        for row in tickets.filter(created_at__date__gte=first_day)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by()
    }
    days = [first_day + timedelta(days=offset) for offset in range(TREND_DAYS)]
    counts = [per_day.get(day, 0) for day in days]
    peak = max(counts)
    trend = [
        {"date": day, "total": count, "percent": _percent(count, peak)}
        for day, count in zip(days, counts)
    ]

    oldest_unassigned = (
        tickets.filter(status__in=ACTIVE_STATUSES, assignee__isnull=True)
        .select_related("category", "requester", "assignee")
        .order_by("created_at", "id")[:5]
    )

    return {
        "stats": stats,
        "by_status": by_status,
        "by_priority": by_priority,
        "categories": categories,
        "workload": workload,
        "trend": trend,
        "oldest_unassigned": oldest_unassigned,
    }
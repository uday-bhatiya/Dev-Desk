from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from accounts.models import Role


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class TicketPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class HistoryField(models.TextChoices):
    STATUS = "status", "Status"
    ASSIGNEE = "assignee", "Assignee"
    PRIORITY = "priority", "Priority"


FINISHED_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="category_name_ci_unique"),
        ]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN
    )
    priority = models.CharField(
        max_length=20, choices=TicketPriority.choices, default=TicketPriority.MEDIUM
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="tickets"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_tickets",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        limit_choices_to={"role__in": [Role.AGENT, Role.ADMIN]},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=TicketStatus.values),
                name="ticket_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(priority__in=TicketPriority.values),
                name="ticket_priority_valid",
            ),
            models.CheckConstraint(
                condition=Q(resolved_at__isnull=True)
                | Q(status__in=[s.value for s in FINISHED_STATUSES]),
                name="ticket_resolved_at_consistent",
            ),
        ]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    @property
    def is_finished(self):
        return self.status in FINISHED_STATUSES

    def save(self, *args, **kwargs):
        if self.is_finished:
            if self.resolved_at is None:
                self.resolved_at = timezone.now()
        else:
            self.resolved_at = None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "resolved_at", "updated_at"}
        super().save(*args, **kwargs)


class Comment(models.Model):
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_comments",
    )
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal notes are visible only to agents and administrators.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["ticket", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(body=""), name="comment_body_not_empty"
            ),
        ]

    def __str__(self):
        return f"Comment {self.pk} on ticket {self.ticket_id}"


class TicketHistory(models.Model):
    """One row per change to a ticket's status, assignee or priority."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="history"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ticket_changes",
    )
    field = models.CharField(max_length=20, choices=HistoryField.choices)
    old_value = models.CharField(max_length=150, blank=True)
    new_value = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "ticket history"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["ticket", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(field__in=HistoryField.values),
                name="history_field_valid",
            ),
            models.CheckConstraint(
                condition=~Q(old_value=F("new_value")),
                name="history_value_changed",
            ),
        ]

    def __str__(self):
        return f"{self.field}: {self.old_value or '-'} -> {self.new_value or '-'}"
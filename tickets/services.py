"""
Business logic for changing tickets.

Views call these functions and never modify tickets directly. Each function:
  1. runs inside a database transaction
  2. re-reads the ticket (locking it where state changes)
  3. checks permissions and business rules against that fresh copy
  4. changes the ticket and records its history together
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from . import permissions
from .models import (
    Comment,
    HistoryField,
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketStatus,
)


class WorkflowError(Exception):
    """A business rule blocks the change"""


TRANSITIONS = {
    TicketStatus.OPEN: (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED),
    TicketStatus.IN_PROGRESS: (TicketStatus.OPEN, TicketStatus.RESOLVED),
    TicketStatus.RESOLVED: (TicketStatus.IN_PROGRESS, TicketStatus.CLOSED),
    TicketStatus.CLOSED: (),
}


def allowed_next_statuses(user, ticket):
    """Status values `user` may move this ticket to right now."""
    if not permissions.can_change_status(user, ticket):
        return []
    current = TicketStatus(ticket.status)
    if current == TicketStatus.CLOSED:
        return [TicketStatus.OPEN.value] if user.is_it_admin else []
    return [status.value for status in TRANSITIONS[current]]


# ---- helpers

def _lock(ticket):
    """Re-read the ticket and lock its row until the transaction ends."""
    return Ticket.objects.select_for_update().get(pk=ticket.pk)


def _record(ticket, user, field, old_value, new_value):
    TicketHistory.objects.create(
        ticket=ticket,
        changed_by=user,
        field=field,
        old_value=old_value,
        new_value=new_value,
    )


# ----- services

def add_comment(user, ticket, body, is_internal=False):
    """Add a comment. Returns the new Comment."""
    with transaction.atomic():
        ticket = Ticket.objects.get(pk=ticket.pk) 
        if not permissions.can_comment(user, ticket):
            raise PermissionDenied
        if is_internal and not permissions.can_post_internal_note(user):
            raise PermissionDenied
        comment = Comment.objects.create(
            ticket=ticket, author=user, body=body, is_internal=is_internal
        )
    
        Ticket.objects.filter(pk=ticket.pk).update(updated_at=timezone.now())
        return comment


def assign_ticket(user, ticket, assignee):
    with transaction.atomic():
        ticket = _lock(ticket)
        if not permissions.assignable_users(user, ticket).filter(pk=assignee.pk).exists():
            raise PermissionDenied
        if ticket.assignee_id == assignee.pk:
            return False
        old_value = ticket.assignee.username if ticket.assignee_id else ""
        ticket.assignee = assignee
        ticket.save(update_fields=["assignee"])
        _record(ticket, user, HistoryField.ASSIGNEE, old_value, assignee.username)
        return True


def change_status(user, ticket, new_status):
    with transaction.atomic():
        ticket = _lock(ticket)
        if not permissions.can_change_status(user, ticket):
            raise PermissionDenied
        if new_status == ticket.status:
            return False
        if new_status not in allowed_next_statuses(user, ticket):
            label = dict(TicketStatus.choices).get(new_status, new_status)
            raise WorkflowError(
                f"A ticket cannot move from {ticket.get_status_display()} to {label}."
            )
        if new_status != TicketStatus.OPEN and ticket.assignee_id is None:
            raise WorkflowError("Assign the ticket to someone before working on it.")
        old_label = ticket.get_status_display()
        ticket.status = new_status
        ticket.save(update_fields=["status"])
        _record(
            ticket, user, HistoryField.STATUS, old_label, ticket.get_status_display()
        )
        return True


def change_priority(user, ticket, new_priority):
    if new_priority not in TicketPriority.values:
        raise WorkflowError("Unknown priority.")
    with transaction.atomic():
        ticket = _lock(ticket)
        if not permissions.can_change_priority(user, ticket):
            raise PermissionDenied
        if new_priority == ticket.priority:
            return False
        old_label = ticket.get_priority_display()
        ticket.priority = new_priority
        ticket.save(update_fields=["priority"])
        _record(
            ticket,
            user,
            HistoryField.PRIORITY,
            old_label,
            ticket.get_priority_display(),
        )
        return True
from accounts.models import Role, User

from .models import Ticket, TicketStatus


   # ----- visibility

def visible_tickets(user):
    if not user.is_authenticated:
        return Ticket.objects.none()
    if user.can_handle_tickets:
        return Ticket.objects.all()
    return Ticket.objects.filter(requester=user)


def can_view_ticket(user, ticket):
    if not user.is_authenticated:
        return False
    return user.can_handle_tickets or ticket.requester_id == user.id


def visible_comments(user, ticket):
    comments = ticket.comments.select_related("author")
    if not user.can_handle_tickets:
        comments = comments.filter(is_internal=False)
    return comments

    # ---  actions

def can_comment(user, ticket):
    if not can_view_ticket(user, ticket):
        return False
    if user.can_handle_tickets:
        return True
    return ticket.status != TicketStatus.CLOSED


def can_post_internal_note(user):
    return user.is_authenticated and user.can_handle_tickets


def _can_work_on(user, ticket):
    if not user.is_authenticated:
        return False
    if user.is_it_admin:
        return True
    return user.is_agent and ticket.assignee_id == user.id


def can_change_status(user, ticket):
    return _can_work_on(user, ticket)


def can_change_priority(user, ticket):
    return _can_work_on(user, ticket)


def assignable_users(user, ticket):
    if not user.is_authenticated:
        return User.objects.none()
    if user.is_it_admin:
        return User.objects.filter(
            is_active=True, role__in=[Role.AGENT, Role.ADMIN]
        )
    if user.is_agent and ticket.assignee_id in (None, user.id):
        return User.objects.filter(pk=user.pk)  # agents can only take it themselves
    return User.objects.none()


def can_assign(user, ticket):
    return assignable_users(user, ticket).exists()
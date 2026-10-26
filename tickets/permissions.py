from .models import Ticket


def visible_tickets(user):
    if not user.is_authenticated:
        return Ticket.objects.none()
    if user.can_handle_tickets:
        return Ticket.objects.all()
    return Ticket.objects.filter(requester=user)


def visible_comments(user, ticket):
    comments = ticket.comments.select_related("author")
    if not user.can_handle_tickets:
        comments = comments.filter(is_internal=False)
    return comments
from accounts.models import Role, User
from tickets.models import Category, Ticket

PASSWORD = "Test-pass-12345"


def make_user(username, role=Role.EMPLOYEE, **extra):
    return User.objects.create_user(
        username=username, password=PASSWORD, role=role, **extra
    )


def make_category(name="Hardware"):
    category, _ = Category.objects.get_or_create(name=name)
    return category


def make_ticket(requester, assignee=None, title="Printer is broken", **extra):
    fields = {
        "description": "The printer on floor 2 does not print anything.",
        "category": make_category(),
    }
    fields.update(extra)
    return Ticket.objects.create(
        title=title, requester=requester, assignee=assignee, **fields
    )
from django import forms
from django.db.models import Case, IntegerField, Q, When

from .models import Category, TicketPriority, TicketStatus

ACTIVE_STATUSES = (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)

PRIORITY_RANK = Case(
    When(priority=TicketPriority.URGENT, then=0),
    When(priority=TicketPriority.HIGH, then=1),
    When(priority=TicketPriority.MEDIUM, then=2),
    default=3,
    output_field=IntegerField(),
)

SORT_CHOICES = [
    ("newest", "Newest first"),
    ("oldest", "Oldest first"),
    ("updated", "Recently updated"),
    ("priority", "Highest priority"),
]


class TicketFilterForm(forms.Form):

    q = forms.CharField(
        required=False,
        max_length=100,
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Title, description or ticket number"}
        ),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "Any status"), *TicketStatus.choices],
    )
    priority = forms.ChoiceField(
        required=False,
        label="Priority",
        choices=[("", "Any priority"), *TicketPriority.choices],
    )
    category = forms.ModelChoiceField(
        required=False,
        label="Category",
        queryset=Category.objects.all(),
        empty_label="Any category",
    )
    assignment = forms.ChoiceField(
        required=False,
        label="Assignment",
        choices=[("", "Anyone"), ("me", "Assigned to me"), ("unassigned", "Unassigned")],
    )
    sort = forms.ChoiceField(required=False, label="Sort by", choices=SORT_CHOICES)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if not user.can_handle_tickets:
            del self.fields["assignment"]


def _search(queryset, text, user):
    for term in text.split()[:5]:
        condition = Q(title__icontains=term) | Q(description__icontains=term)
        digits = term.lstrip("#")
        if digits.isascii() and digits.isdigit() and len(digits) <= 9:
            condition |= Q(pk=int(digits))
        if user.can_handle_tickets:
            condition |= Q(requester__username__icontains=term)
        queryset = queryset.filter(condition)
    return queryset


def apply_filters(queryset, user, data):
    text = (data.get("q") or "").strip()
    if text:
        queryset = _search(queryset, text, user)
    if data.get("status"):
        queryset = queryset.filter(status=data["status"])
    if data.get("priority"):
        queryset = queryset.filter(priority=data["priority"])
    if data.get("category"):
        queryset = queryset.filter(category=data["category"])
    assignment = data.get("assignment")
    if assignment == "me":
        queryset = queryset.filter(assignee=user)
    elif assignment == "unassigned":
        queryset = queryset.filter(assignee__isnull=True)
    return queryset


def apply_sort(queryset, key):
    if key == "oldest":
        return queryset.order_by("created_at", "id")
    if key == "updated":
        return queryset.order_by("-updated_at", "-id")
    if key == "priority":
        return queryset.annotate(priority_rank=PRIORITY_RANK).order_by(
            "priority_rank", "-created_at", "-id"
        )
    return queryset.order_by("-created_at", "-id")
from django import forms

from accounts.models import User

from . import permissions, services
from .models import Category, Comment, Ticket, TicketPriority, TicketStatus


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "category", "description"]
        labels = {"title": "Summary"}
        help_texts = {"title": "A short description of the problem."}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Select a category"

    def clean_title(self):
        title = self.cleaned_data["title"]
        if len(title) < 5:
            raise forms.ValidationError("Please enter at least 5 characters.")
        return title

    def clean_description(self):
        description = self.cleaned_data["description"]
        if len(description) < 10:
            raise forms.ValidationError(
                "Please describe the problem in at least 10 characters."
            )
        return description


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body", "is_internal"]
        labels = {"body": "", "is_internal": "Internal note (hidden from the requester)"}
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Write a comment..."}
            ),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        if not permissions.can_post_internal_note(user):
            del self.fields["is_internal"]


class TicketStatusForm(forms.Form):
    status = forms.ChoiceField(label="Status")

    def __init__(self, *args, user, ticket, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = services.allowed_next_statuses(user, ticket)
        self.fields["status"].choices = [("", "Change status to...")] + [
            (value, TicketStatus(value).label) for value in allowed
        ]


class TicketPriorityForm(forms.Form):
    priority = forms.ChoiceField(label="Priority")

    def __init__(self, *args, ticket, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["priority"].choices = [("", "Change priority to...")] + [
            (p.value, p.label) for p in TicketPriority if p.value != ticket.priority
        ]


def _user_label(user):
    return f"{user.get_full_name() or user.username} ({user.get_role_display()})"


class TicketAssignForm(forms.Form):
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(), empty_label="Assign to...", label="Assignee"
    )

    def __init__(self, *args, user, ticket, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["assignee"]
        field.queryset = (
            permissions.assignable_users(user, ticket)
            .exclude(pk=ticket.assignee_id)
            .order_by("username")
        )
        field.label_from_instance = _user_label
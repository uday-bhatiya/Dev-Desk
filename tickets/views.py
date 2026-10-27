from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import agent_required

from . import permissions, services
from .forms import (
    CommentForm,
    TicketAssignForm,
    TicketCreateForm,
    TicketPriorityForm,
    TicketStatusForm,
)
from .models import TicketPriority, TicketStatus

PRIORITY_RANK = Case(
    When(priority=TicketPriority.URGENT, then=0),
    When(priority=TicketPriority.HIGH, then=1),
    When(priority=TicketPriority.MEDIUM, then=2),
    default=3,
    output_field=IntegerField(),
)


def _get_ticket(request, pk):
    return get_object_or_404(permissions.visible_tickets(request.user), pk=pk)


def _flash_errors(request, form):
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)


def home(request):
    return redirect("ticket_list")


@login_required
def ticket_list(request):
    tickets = permissions.visible_tickets(request.user).select_related(
        "category", "requester", "assignee"
    )
    return render(request, "tickets/ticket_list.html", {"tickets": tickets})


@agent_required
def ticket_queue(request):
    active = (
        permissions.visible_tickets(request.user)
        .filter(status__in=[TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
        .select_related("category", "requester", "assignee")
        .annotate(priority_rank=PRIORITY_RANK)
        .order_by("priority_rank", "created_at")
    )
    context = {
        "mine": active.filter(assignee=request.user),
        "unassigned": active.filter(assignee__isnull=True),
    }
    return render(request, "tickets/ticket_queue.html", context)


@login_required
def ticket_detail(request, pk):
    user = request.user
    ticket = get_object_or_404(
        permissions.visible_tickets(user).select_related(
            "category", "requester", "assignee"
        ),
        pk=pk,
    )

    assign_form = TicketAssignForm(user=user, ticket=ticket)
    if not assign_form.fields["assignee"].queryset.exists():
        assign_form = None

    context = {
        "ticket": ticket,
        "comments": permissions.visible_comments(user, ticket),
        "history": ticket.history.select_related("changed_by"),
        "comment_form": (
            CommentForm(user=user) if permissions.can_comment(user, ticket) else None
        ),
        "status_form": (
            TicketStatusForm(user=user, ticket=ticket)
            if services.allowed_next_statuses(user, ticket)
            else None
        ),
        "priority_form": (
            TicketPriorityForm(ticket=ticket)
            if permissions.can_change_priority(user, ticket)
            else None
        ),
        "assign_form": assign_form,
    }
    return render(request, "tickets/ticket_detail.html", context)


@login_required
def ticket_create(request):
    if request.method == "POST":
        form = TicketCreateForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.requester = request.user
            ticket.save()
            messages.success(request, f"Ticket #{ticket.pk} was created.")
            return redirect("ticket_detail", pk=ticket.pk)
    else:
        form = TicketCreateForm()
    return render(request, "tickets/ticket_form.html", {"form": form})


# --- POST-only actions

@login_required
@require_POST
def ticket_add_comment(request, pk):
    ticket = _get_ticket(request, pk)
    if not permissions.can_comment(request.user, ticket):
        raise PermissionDenied
    form = CommentForm(request.POST, user=request.user)
    if form.is_valid():
        services.add_comment(
            request.user,
            ticket,
            form.cleaned_data["body"],
            form.cleaned_data.get("is_internal", False),
        )
        messages.success(request, "Comment added.")
    else:
        _flash_errors(request, form)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_change_status(request, pk):
    ticket = _get_ticket(request, pk)
    if not permissions.can_change_status(request.user, ticket):
        raise PermissionDenied
    form = TicketStatusForm(request.POST, user=request.user, ticket=ticket)
    if form.is_valid():
        try:
            changed = services.change_status(
                request.user, ticket, form.cleaned_data["status"]
            )
        except services.WorkflowError as error:
            messages.error(request, str(error))
        else:
            if changed:
                messages.success(request, "Status updated.")
            else:
                messages.info(request, "No change was made.")
    else:
        _flash_errors(request, form)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_change_priority(request, pk):
    ticket = _get_ticket(request, pk)
    if not permissions.can_change_priority(request.user, ticket):
        raise PermissionDenied
    form = TicketPriorityForm(request.POST, ticket=ticket)
    if form.is_valid():
        try:
            changed = services.change_priority(
                request.user, ticket, form.cleaned_data["priority"]
            )
        except services.WorkflowError as error:
            messages.error(request, str(error))
        else:
            if changed:
                messages.success(request, "Priority updated.")
            else:
                messages.info(request, "No change was made.")
    else:
        _flash_errors(request, form)
    return redirect("ticket_detail", pk=ticket.pk)


@login_required
@require_POST
def ticket_assign(request, pk):
    ticket = _get_ticket(request, pk)
    if not permissions.can_assign(request.user, ticket):
        raise PermissionDenied
    form = TicketAssignForm(request.POST, user=request.user, ticket=ticket)
    if form.is_valid():
        changed = services.assign_ticket(
            request.user, ticket, form.cleaned_data["assignee"]
        )
        if changed:
            messages.success(request, "Ticket assigned.")
        else:
            messages.info(request, "No change was made.")
    else:
        _flash_errors(request, form)
    return redirect("ticket_detail", pk=ticket.pk)
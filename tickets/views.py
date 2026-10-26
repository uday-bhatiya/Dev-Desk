from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TicketCreateForm
from .permissions import visible_comments, visible_tickets


def home(request):
    return redirect("ticket_list")


@login_required
def ticket_list(request):
    tickets = visible_tickets(request.user).select_related(
        "category", "requester", "assignee"
    )
    return render(request, "tickets/ticket_list.html", {"tickets": tickets})


@login_required
def ticket_detail(request, pk):
    queryset = visible_tickets(request.user).select_related(
        "category", "requester", "assignee"
    )
    ticket = get_object_or_404(queryset, pk=pk)
    context = {
        "ticket": ticket,
        "comments": visible_comments(request.user, ticket),
        "history": ticket.history.select_related("changed_by"),
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
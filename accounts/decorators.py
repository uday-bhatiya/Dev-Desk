from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def agent_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.can_handle_tickets:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)
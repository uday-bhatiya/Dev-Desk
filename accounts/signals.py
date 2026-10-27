from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from . import throttle


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    username = throttle.normalize_username(credentials.get("username"))
    throttle.record_failure(username, throttle.client_ip(request))


@receiver(user_logged_in)
def clear_failed_logins(sender, request, user, **kwargs):
    if request is None:
        return
    username = throttle.normalize_username(user.get_username())
    throttle.clear_failures(username, throttle.client_ip(request))
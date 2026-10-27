import ipaddress
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LoginAttempt

logger = logging.getLogger("devdesk.security")

MAX_FAILURES_PER_ACCOUNT_AND_IP = 5
MAX_FAILURES_PER_IP = 20
WINDOW = timedelta(minutes=15) 
RETENTION = timedelta(days=1)    


def normalize_username(username):
    return (username or "").strip().lower()[:150]


def _valid_ip(value):
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_ip(request):
    if request is None:
        return None
    candidate = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "THROTTLE_TRUST_PROXY_HEADER", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            candidate = forwarded.split(",")[-1].strip()
    return _valid_ip(candidate)


def is_blocked(username, ip):
    recent = LoginAttempt.objects.filter(created_at__gte=timezone.now() - WINDOW)
    if (
        recent.filter(username=username, ip_address=ip).count()
        >= MAX_FAILURES_PER_ACCOUNT_AND_IP
    ):
        return True
    return ip is not None and recent.filter(ip_address=ip).count() >= MAX_FAILURES_PER_IP


def record_failure(username, ip):
    LoginAttempt.objects.create(username=username, ip_address=ip)
    LoginAttempt.objects.filter(created_at__lt=timezone.now() - RETENTION).delete()
    if is_blocked(username, ip):
        logger.warning("Login throttled for ip=%s", ip)


def clear_failures(username, ip):
    LoginAttempt.objects.filter(username=username, ip_address=ip).delete()
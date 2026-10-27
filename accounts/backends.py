from django.contrib.auth.backends import ModelBackend

from . import throttle


class ThrottledModelBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is not None and username:
            key = throttle.normalize_username(username)
            if throttle.is_blocked(key, throttle.client_ip(request)):
                return None
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )
from django import forms
from django.contrib.auth.forms import AuthenticationForm

from . import throttle


class ThrottledAuthenticationForm(AuthenticationForm):

    def clean(self):
        username = throttle.normalize_username(self.cleaned_data.get("username"))
        if username and throttle.is_blocked(
            username, throttle.client_ip(self.request)
        ):
            raise forms.ValidationError(
                "Too many failed login attempts. Please wait 15 minutes and try again.",
                code="throttled",
            )
        return super().clean()
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create the first administrator from environment variables if it does "
        "not exist yet. Safe to run on every deploy."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")

        if not username or not password:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD is not set; "
                "skipping administrator creation."
            )
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Administrator '{username}' already exists; leaving it unchanged.")
            return

        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(
                "DJANGO_SUPERUSER_PASSWORD is too weak: " + " ".join(error.messages)
            )

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created administrator '{username}'."))
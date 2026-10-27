from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    EMPLOYEE = "employee", "Employee"
    AGENT = "agent", "Support Agent"
    ADMIN = "admin", "Administrator"


class User(AbstractUser):

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values),
                name="user_role_valid",
            ),
        ]

    @property
    def is_it_admin(self):
        return self.is_superuser or self.role == Role.ADMIN

    @property
    def is_agent(self):
        return self.role == Role.AGENT

    @property
    def is_employee(self):
        return self.role == Role.EMPLOYEE

    @property
    def can_handle_tickets(self):
        return self.is_agent or self.is_it_admin

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = Role.ADMIN
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "role"}
        super().save(*args, **kwargs)


class LoginAttempt(models.Model):

    username = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["username", "ip_address", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.username or '-'} from {self.ip_address or 'unknown'}"
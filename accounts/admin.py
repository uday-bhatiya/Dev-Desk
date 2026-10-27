from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LoginAttempt, User

@admin.register(User)
class DevDeskUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = UserAdmin.list_filter + ("role",)
    fieldsets = UserAdmin.fieldsets + (("DevDesk", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("DevDesk", {"fields": ("role",)}),)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Read-only. An administrator can delete rows to unlock someone early."""

    list_display = ("created_at", "username", "ip_address")
    search_fields = ("username",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
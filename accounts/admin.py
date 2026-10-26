from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

@admin.register(User)
class DevDeskUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = UserAdmin.list_filter + ("role",)
    fieldsets = UserAdmin.fieldsets + (("DevDesk", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("DevDesk", {"fields": ("role",)}),)
from django.contrib import admin

from .models import Category, Comment, Ticket, TicketHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    autocomplete_fields = ("author",)


class TicketHistoryInline(admin.TabularInline):
    """Read-only audit trail: history is never edited by hand."""

    model = TicketHistory
    extra = 0
    can_delete = False
    fields = ("created_at", "changed_by", "field", "old_value", "new_value")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "status", "priority", "category",
        "requester", "assignee", "created_at",
    )
    list_filter = ("status", "priority", "category")
    search_fields = ("title", "description", "requester__username", "assignee__username")
    list_select_related = ("category", "requester", "assignee")
    autocomplete_fields = ("requester", "assignee", "category")
    readonly_fields = ("created_at", "updated_at", "resolved_at")
    date_hierarchy = "created_at"
    inlines = [CommentInline, TicketHistoryInline]
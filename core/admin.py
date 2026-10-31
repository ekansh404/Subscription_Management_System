from django.contrib import admin

from .models import OutboxEmail, Sequence


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ("key", "last_value")
    readonly_fields = ("key", "last_value")

    def has_add_permission(self, request):
        return False


@admin.register(OutboxEmail)
class OutboxEmailAdmin(admin.ModelAdmin):
    list_display = ("created_at", "to", "subject")
    search_fields = ("to", "subject")

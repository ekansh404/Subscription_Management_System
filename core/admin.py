from django.contrib import admin

from .models import Sequence


@admin.register(Sequence)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ("key", "last_value")
    readonly_fields = ("key", "last_value")

    def has_add_permission(self, request):
        return False

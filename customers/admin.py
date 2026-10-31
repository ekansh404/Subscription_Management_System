from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "city", "is_active", "user")
    list_filter = ("is_active", "country")
    search_fields = ("name", "company", "email", "phone", "tax_id")
    raw_id_fields = ("user",)

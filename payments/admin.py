from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("number", "invoice", "customer", "method", "amount", "payment_date")
    list_filter = ("method",)
    search_fields = ("number", "invoice__number", "customer__name", "reference")

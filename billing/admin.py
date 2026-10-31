from django.contrib import admin

from .models import Discount, Invoice, InvoiceDiscount, InvoiceLine


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class InvoiceDiscountInline(admin.TabularInline):
    model = InvoiceDiscount
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "customer_name", "invoice_date", "due_date", "status", "amount_total", "amount_paid")
    list_filter = ("status",)
    search_fields = ("number", "customer_name", "customer_email")
    inlines = [InvoiceLineInline, InvoiceDiscountInline]


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "discount_type", "value", "scope", "used_count", "usage_limit", "is_active")
    filter_horizontal = ("products", "subscriptions")

from django.contrib import admin

from .models import QuotationTemplate, QuotationTemplateLine, Subscription, SubscriptionEvent, SubscriptionLine


class TemplateLineInline(admin.TabularInline):
    model = QuotationTemplateLine
    extra = 0


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "validity_days", "duration_periods", "is_active")
    inlines = [TemplateLineInline]


class SubscriptionLineInline(admin.TabularInline):
    model = SubscriptionLine
    extra = 0


class SubscriptionEventInline(admin.TabularInline):
    model = SubscriptionEvent
    extra = 0
    readonly_fields = ("created_at", "user", "from_status", "to_status", "message")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "plan", "status", "start_date", "next_invoice_date", "amount_total")
    list_filter = ("status", "plan")
    search_fields = ("number", "customer__name")
    inlines = [SubscriptionLineInline, SubscriptionEventInline]

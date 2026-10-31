from django.apps import AppConfig

from core.navigation import ADMIN, MenuItem


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing"

    menu = (
        MenuItem("Invoices", "billing:invoice_list", icon="file-text", order=50, match="billing:invoice"),
        MenuItem("Billing run", "billing:run", icon="calendar", order=51, match="billing:run"),
        MenuItem("Discounts", "billing:discount_list", icon="tag", roles=(ADMIN,), order=82, match="billing:discount"),
    )

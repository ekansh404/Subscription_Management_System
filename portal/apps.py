from django.apps import AppConfig

from core.navigation import CUSTOMER, MenuItem


class PortalConfig(AppConfig):
    """Customer self-service: customers see and manage only their own data."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = "Customer portal"

    menu = (
        MenuItem("Overview", "portal:home", icon="home", roles=(CUSTOMER,), order=10, match="portal:home"),
        MenuItem("My subscriptions", "portal:subscription_list", icon="repeat", roles=(CUSTOMER,), order=11, match="portal:subscription"),
        MenuItem("My invoices", "portal:invoice_list", icon="file-text", roles=(CUSTOMER,), order=12, match="portal:invoice"),
        MenuItem("My payments", "portal:payment_list", icon="credit-card", roles=(CUSTOMER,), order=13, match="portal:payment"),
    )

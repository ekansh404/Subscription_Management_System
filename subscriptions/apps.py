from django.apps import AppConfig

from core.navigation import MenuItem


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "subscriptions"
    verbose_name = "Subscriptions"

    menu = (
        MenuItem("Subscriptions", "subscriptions:subscription_list", icon="repeat", order=40, match="subscriptions:subscription"),
        MenuItem("Quotation templates", "subscriptions:template_list", icon="clipboard", order=41, match="subscriptions:template"),
    )

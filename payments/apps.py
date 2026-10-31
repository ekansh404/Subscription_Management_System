from django.apps import AppConfig

from core.navigation import MenuItem


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"
    verbose_name = "Payments"

    menu = (
        MenuItem("Payments", "payments:payment_list", icon="credit-card", order=55, match="payments:payment"),
        MenuItem("Receivables", "payments:receivables", icon="wallet", order=56, match="payments:receivables"),
    )

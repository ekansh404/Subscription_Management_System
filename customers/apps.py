from django.apps import AppConfig

from core.navigation import MenuItem


class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "customers"
    verbose_name = "Customers"

    menu = (MenuItem("Customers", "customers:list", icon="users", order=20),)

    def ready(self):
        from . import signals  # noqa: F401  (connects the portal-account linking signal)

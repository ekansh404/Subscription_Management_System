from django.apps import AppConfig

from core.navigation import ADMIN, MenuItem


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    verbose_name = "REST API"

    menu = (MenuItem("REST API", "api:api-root", icon="server", roles=(ADMIN,), order=95),)

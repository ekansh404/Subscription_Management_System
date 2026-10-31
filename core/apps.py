from django.apps import AppConfig

from .navigation import ADMIN, MenuItem


class CoreConfig(AppConfig):
    """Foundation app: base layout, shared models, navigation registry, helpers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core"

    menu = (MenuItem("Email outbox", "core:outbox", icon="mail", roles=(ADMIN,), order=97, match="core:outbox"),)

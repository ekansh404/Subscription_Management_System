from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Foundation app: base layout, shared models, navigation registry, helpers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Core"

    # Core has no navigation entries of its own; the brand link goes home.
    menu = ()

from django.apps import AppConfig

from core.navigation import ADMIN, MenuItem


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"

    menu = (MenuItem("Staff", "accounts:staff_list", icon="shield", roles=(ADMIN,), order=90),)

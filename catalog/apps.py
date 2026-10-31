from django.apps import AppConfig

from core.navigation import ADMIN, MenuItem


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Catalog"

    menu = (
        MenuItem("Products", "catalog:product_list", icon="package", order=30, match="catalog:product"),
        MenuItem("Plans", "catalog:plan_list", icon="layers", order=31, match="catalog:plan"),
        MenuItem("Taxes", "catalog:tax_list", icon="percent", roles=(ADMIN,), order=80, match="catalog:tax"),
        MenuItem("Attributes", "catalog:attribute_list", icon="sliders", roles=(ADMIN,), order=81, match="catalog:attribute"),
    )

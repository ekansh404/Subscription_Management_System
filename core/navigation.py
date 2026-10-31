"""
Navigation registry.

Every app declares the sidebar entries it contributes on its ``AppConfig``::

    class CustomersConfig(AppConfig):
        menu = (MenuItem("Customers", "customers:list", icon="users", order=20),)

The sidebar is then assembled from whatever apps are installed and filtered by
the current user's role, so adding or removing an app never requires touching
the layout template.
"""

from dataclasses import dataclass

from django.apps import apps

ADMIN = "admin"
STAFF = "staff"
CUSTOMER = "customer"


@dataclass(frozen=True)
class MenuItem:
    label: str
    url_name: str  # namespaced URL name, e.g. "customers:list"
    icon: str = "circle"  # key in core.icons.ICONS
    roles: tuple[str, ...] = (ADMIN, STAFF)
    order: int = 50
    # Highlight this entry for every URL name starting with ``match``
    # (e.g. "catalog:plan"); defaults to the whole URL namespace.
    match: str = ""

    @property
    def namespace(self) -> str:
        """URL namespace used to highlight the active sidebar entry."""
        return self.url_name.split(":", 1)[0]

    def is_active_for(self, view_name: str) -> bool:
        if self.match:
            return view_name.startswith(self.match)
        return view_name.split(":", 1)[0] == self.namespace

    def visible_to(self, user) -> bool:
        return getattr(user, "role", None) in self.roles


def menu_for(user) -> list[MenuItem]:
    """Sidebar entries visible to ``user``, sorted by ``order`` then label."""
    if not getattr(user, "is_authenticated", False):
        return []
    items = [
        item
        for config in apps.get_app_configs()
        for item in getattr(config, "menu", ())
        if item.visible_to(user)
    ]
    return sorted(items, key=lambda item: (item.order, item.label))

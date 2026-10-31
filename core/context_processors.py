from django.conf import settings

from .navigation import menu_for


def app_context(request):
    """Branding, currency and the role-filtered sidebar for every template."""
    user = getattr(request, "user", None)
    resolver_match = getattr(request, "resolver_match", None)
    return {
        "app_name": settings.APP_NAME,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "currency_code": settings.CURRENCY_CODE,
        "menu_items": menu_for(user),
        "current_namespace": resolver_match.namespace if resolver_match else "",
    }

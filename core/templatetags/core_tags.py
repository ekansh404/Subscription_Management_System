from decimal import Decimal, InvalidOperation

from django import forms, template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.icons import ICONS
from core.utils.money import format_money

register = template.Library()


@register.filter
def money(value):
    """Format a number as currency using the configured symbol: ``{{ invoice.amount_total|money }}``."""
    if value is None or value == "":
        return "-"
    try:
        return format_money(Decimal(str(value)), settings.CURRENCY_SYMBOL)
    except (InvalidOperation, ValueError):
        return value


@register.filter
def percent(value):
    """``18.00 -> '18%'``, ``12.50 -> '12.5%'``."""
    if value is None or value == "":
        return "-"
    try:
        number = Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return value
    return f"{number:f}%"


@register.simple_tag
def icon(name, css_class=""):
    """Inline SVG icon from the offline icon set: ``{% icon "users" "me-2" %}``."""
    body = ICONS.get(name) or ICONS["circle"]
    return format_html(
        '<svg class="icon {}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>',
        css_class,
        mark_safe(body),
    )


@register.simple_tag
def status_badge(value, label=None):
    """Coloured pill for a workflow status: ``{% status_badge sub.status sub.get_status_display %}``."""
    label = label or str(value).replace("_", " ").title()
    return format_html('<span class="badge status-badge status-{}">{}</span>', value, label)


@register.simple_tag
def elided_pages(page_obj):
    """Page numbers with ellipsis for long paginators (``1 … 4 5 6 … 20``)."""
    return list(page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1))


@register.filter
def add_class(bound_field, css_class):
    """Render a form field with extra CSS classes (used to flag validation errors)."""
    existing = bound_field.field.widget.attrs.get("class", "")
    return bound_field.as_widget(attrs={"class": f"{existing} {css_class}".strip()})


@register.filter
def is_checkbox(bound_field):
    return isinstance(bound_field.field.widget, forms.CheckboxInput)


@register.filter
def is_multi_choice(bound_field):
    return isinstance(bound_field.field.widget, (forms.CheckboxSelectMultiple, forms.RadioSelect))


@register.filter
def initials(name):
    parts = [part for part in str(name or "").split() if part]
    if not parts:
        return "?"
    return "".join(part[0] for part in parts[:2]).upper()


@register.filter
def get_item(mapping, key):
    """Dictionary lookup in templates: ``{{ counts|get_item:status }}``."""
    if mapping is None:
        return None
    return mapping.get(key)


@register.filter
def subtract(value, arg):
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except (InvalidOperation, ValueError, TypeError):
        return ""

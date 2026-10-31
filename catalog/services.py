"""
Variant generation.

A product offered with, say, Brand {Odoo, Generic} and Edition {Cloud, On-prem}
gets four variants. Choosing a value adds its ``price_extra`` to the price.
Re-running is safe: existing variants are kept (their history stays intact),
new combinations are created and combinations no longer offered are archived.
"""

from itertools import groupby, product as cartesian

from django.db import transaction

from .models import Product, ProductVariant


def _combinations(product: Product) -> list[tuple]:
    values = sorted(product.attribute_values.select_related("attribute"), key=lambda v: (v.attribute.name, v.sequence, v.name))
    groups = [list(group) for _, group in groupby(values, key=lambda v: v.attribute_id)]
    if not groups:
        return [()]
    return list(cartesian(*groups))


@transaction.atomic
def generate_variants(product: Product) -> list[ProductVariant]:
    """Create/refresh the variants of ``product``; return the active ones."""
    active_keys = set()
    for combo in _combinations(product):
        key = "-".join(str(value.pk) for value in sorted(combo, key=lambda v: v.pk))
        suffix = ", ".join(value.name for value in combo)
        variant, created = ProductVariant.objects.get_or_create(
            product=product,
            combination_key=key,
            defaults={"name": product.name},
        )
        variant.name = f"{product.name} ({suffix})" if suffix else product.name
        variant.price_extra = sum((value.price_extra for value in combo), 0)
        variant.is_active = product.is_active
        variant.save()
        if created and combo:
            variant.values.set(combo)
        active_keys.add(key)
    product.variants.exclude(combination_key__in=active_keys).update(is_active=False)
    return list(product.variants.filter(is_active=True))

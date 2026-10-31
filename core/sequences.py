"""
Atomic document numbering.

Numbers are handed out inside a transaction with a row lock, so two billing
runs (or two staff members clicking "Create invoice" at the same moment) can
never produce the same invoice number.
"""

from django.db import transaction

from .models import Sequence


def next_number(key: str, *, prefix: str, width: int = 5, separator: str = "-") -> str:
    """
    Return the next formatted number for ``key``.

    >>> next_number("subscription", prefix="SUB")        # 'SUB-00001'
    >>> next_number("invoice-2026", prefix="INV/2026", separator="/")  # 'INV/2026/00001'
    """
    with transaction.atomic():
        sequence, _ = Sequence.objects.select_for_update().get_or_create(key=key)
        sequence.last_value += 1
        sequence.save(update_fields=["last_value"])
        return f"{prefix}{separator}{sequence.last_value:0{width}d}"

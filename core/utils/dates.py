"""
Calendar arithmetic for recurring billing, without external dependencies.

Billing periods are identified by the string codes used by
``catalog.models.BillingPeriod`` so this module stays free of model imports.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"

# How many of each period fit in one month; used to normalise recurring
# revenue to MRR (monthly recurring revenue).
MONTHLY_FACTOR = {
    DAILY: Decimal("30"),
    WEEKLY: Decimal("52") / Decimal("12"),
    MONTHLY: Decimal("1"),
    YEARLY: Decimal("1") / Decimal("12"),
}


def add_months(value: date, months: int) -> date:
    """Add ``months`` to ``value``, clamping the day to the end of the month (Jan 31 + 1 month = Feb 28/29)."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_period(value: date, period: str, count: int = 1) -> date:
    """Advance ``value`` by ``count`` billing periods."""
    if period == DAILY:
        return value + timedelta(days=count)
    if period == WEEKLY:
        return value + timedelta(weeks=count)
    if period == MONTHLY:
        return add_months(value, count)
    if period == YEARLY:
        return add_months(value, 12 * count)
    raise ValueError(f"Unknown billing period: {period!r}")


def period_end(start: date, period: str) -> date:
    """Last day covered by a period that starts on ``start`` (inclusive)."""
    return add_period(start, period) - timedelta(days=1)


def monthly_amount(amount: Decimal, period: str) -> Decimal:
    """Normalise an amount billed every ``period`` to a monthly figure."""
    return (Decimal(amount) * MONTHLY_FACTOR[period]).quantize(Decimal("0.01"))

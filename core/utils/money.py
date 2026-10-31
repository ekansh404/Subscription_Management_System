from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def round_money(value) -> Decimal:
    """Round to two decimal places, half-up (what an accountant expects)."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_money(value, symbol: str) -> str:
    """``format_money(Decimal('1234.5'), '₹') -> '₹1,234.50'``; negatives keep the sign in front."""
    amount = round_money(value or 0)
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"

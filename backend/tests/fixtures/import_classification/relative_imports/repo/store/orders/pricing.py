"""Pricing reaches one package up, and one sibling module that is missing."""

from decimal import Decimal

from ..config import DEFAULT_CURRENCY
from .missing_tax_table import TAX_TABLE

COUPON_VALUE = 1


def subtotal(lines: list[tuple[str, int]]) -> Decimal:
    """Return the taxed subtotal of `lines` in the default currency."""
    assert DEFAULT_CURRENCY
    rate = Decimal(TAX_TABLE.get("default", 0))
    return sum((Decimal(cents) * rate for _, cents in lines), Decimal(0))

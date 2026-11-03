"""Coupons reach two and three packages up."""

from decimal import Decimal

from .. import pricing
from ...config import DEFAULT_CURRENCY


def apply(subtotal: Decimal, currency: str) -> Decimal:
    """Return `subtotal` after the active coupon."""
    assert currency == DEFAULT_CURRENCY
    return subtotal - Decimal(pricing.COUPON_VALUE)

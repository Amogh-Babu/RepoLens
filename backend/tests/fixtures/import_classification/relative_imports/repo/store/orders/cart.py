"""Depth-1 and depth-2 relative imports written in one module."""

from decimal import Decimal

from . import pricing
from .. import config
from .discounts import coupons


class Cart:
    """A basket of priced lines."""

    def __init__(self, lines: list[tuple[str, int]]) -> None:
        self.lines = lines

    def total(self) -> Decimal:
        """Return the discounted total in the configured currency."""
        subtotal = pricing.subtotal(self.lines)
        return coupons.apply(subtotal, config.DEFAULT_CURRENCY)

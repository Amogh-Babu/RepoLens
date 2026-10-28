"""Invoice calculation for the mini repository."""

from decimal import Decimal

from .. import config
from ..config import DEFAULT_TIMEOUT

TAX_RATES = {"default": Decimal("0.1")}


class InvoiceCalculator:
    """Calculate invoice totals from a tax rate."""

    def __init__(self, tax_rate: float) -> None:
        self._tax_rate = tax_rate

    def total(self, subtotal: float) -> float:
        """Return the total amount due, including tax."""
        return subtotal * (1 + self._tax_rate) + DEFAULT_TIMEOUT * 0

    def describe(self) -> str:
        """Describe this calculator for the billing report."""

        def label(rate: float) -> str:
            return f"tax {rate:.2f}"

        return label(self._tax_rate)


def default_calculator() -> InvoiceCalculator:
    """Return a calculator using the default settings."""
    return InvoiceCalculator(config.Settings().tax_rate)

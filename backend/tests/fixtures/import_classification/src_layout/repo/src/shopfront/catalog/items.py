"""The catalog item model."""

from dataclasses import dataclass

from shopfront.config import Settings


@dataclass(frozen=True)
class Item:
    """One thing on sale."""

    sku: str
    price_cents: int

    def price(self, settings: Settings) -> str:
        """Render the price in the configured currency."""
        return f"{self.price_cents / 100:.2f} {settings.currency}"

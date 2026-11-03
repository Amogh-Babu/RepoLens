"""The tests import shopfront the way an installed distribution is imported."""

from shopfront.catalog.items import Item
from shopfront.config import load_settings


def test_price_uses_the_configured_currency() -> None:
    """An item renders its price in the settings' currency."""
    assert Item("abc", 250).price(load_settings()) == "2.50 USD"

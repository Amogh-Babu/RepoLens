"""Settings read from the environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the shopfront."""

    currency: str = "USD"
    page_size: int = 20


def load_settings() -> Settings:
    """Return the settings the environment asks for."""
    return Settings(currency=os.environ.get("SHOPFRONT_CURRENCY", "USD"))

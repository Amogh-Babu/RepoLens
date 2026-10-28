"""Settings for the mini repository."""

from dataclasses import dataclass

DEFAULT_TIMEOUT = 30
RETRY_LIMIT, BACKOFF_SECONDS = 3, 1.5


@dataclass
class Settings:
    """Runtime settings for a billing run."""

    tax_rate: float = 0.1

    def with_tax_rate(self, tax_rate: float) -> "Settings":
        """Return a copy of these settings using a different tax rate."""
        return Settings(tax_rate=tax_rate)

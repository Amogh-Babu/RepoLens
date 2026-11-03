"""The user model."""

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class User:
    """One account."""

    email: str

    def timeout(self) -> int:
        """Return the timeout this account is served with."""
        return Settings().timeout_seconds

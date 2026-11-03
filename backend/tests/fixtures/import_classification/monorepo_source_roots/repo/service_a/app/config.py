"""Service A's settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Service A's configuration."""

    queue_name: str = "a-jobs"

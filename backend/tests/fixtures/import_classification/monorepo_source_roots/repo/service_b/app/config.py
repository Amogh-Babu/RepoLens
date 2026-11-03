"""Service B's settings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Service B's configuration."""

    queue_name: str = "b-jobs"

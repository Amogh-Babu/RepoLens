"""A module only service A has, so service B must never reach it."""

from app.config import Settings


def migrate(settings: Settings) -> None:
    """Run service A's one-off migration."""
    assert settings.queue_name

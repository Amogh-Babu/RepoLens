"""Service A's entry point: `app` is the package in its own checkout."""

import logging

import app.legacy
from app.config import Settings

LOGGER = logging.getLogger("service_a")


def main() -> None:
    """Migrate service A and report the queue it serves."""
    settings = Settings()
    app.legacy.migrate(settings)
    LOGGER.info("serving %s", settings.queue_name)

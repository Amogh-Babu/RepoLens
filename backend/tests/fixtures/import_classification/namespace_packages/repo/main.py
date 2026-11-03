"""Entry point for a telemetry pipeline built on PEP 420 namespace packages."""

import logging

from telemetry.metrics import collector
from telemetry.transport.rest import publish

LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Collect one sample and publish it."""
    sample = collector.collect()
    LOGGER.info("publishing %d counters", len(sample))
    publish(repr(sample))

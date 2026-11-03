"""Service B's entry point: the same `app` name, a different checkout.

`app.legacy` exists only in service A and is not on service B's import path,
so Python runs service B's own `app/__init__.py` and then fails to find the
submodule. That package is the nearest module this reference really reaches.
"""

import logging

import app.legacy
from app.config import Settings

LOGGER = logging.getLogger("service_b")


def main() -> None:
    """Report the queue service B serves."""
    LOGGER.info("serving %s", Settings().queue_name)

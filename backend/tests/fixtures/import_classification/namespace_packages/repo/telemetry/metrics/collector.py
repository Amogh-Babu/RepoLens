"""Counters. Neither telemetry/ nor telemetry/metrics/ has an __init__.py."""

from collections import Counter

from . import exporter

COUNTERS: Counter[str] = Counter()


def collect() -> dict[str, int]:
    """Flush the buffer and return the counters recorded so far."""
    exporter.flush()
    return dict(COUNTERS)

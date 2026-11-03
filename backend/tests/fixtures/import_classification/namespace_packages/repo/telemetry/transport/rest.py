"""HTTP transport for samples.

`telemetry.metrics` and `telemetry.transport` are namespace packages: they are
importable but no file runs for them, so a reference to the package itself
reaches no module in this repository.
"""

import urllib.request

import requests

import telemetry.metrics
from telemetry.transport import missing_retry


def publish(payload: str) -> None:
    """POST one payload, retrying through the (missing) retry helper."""
    telemetry.metrics.record(payload)
    missing_retry.backoff()
    requests.post("https://example.invalid/samples", data=payload)
    urllib.request.urlopen("https://example.invalid/ping")

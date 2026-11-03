"""Serialize buffered samples and hand them to the transport."""

import json

from telemetry.transport import rest

BUFFER: list[dict[str, int]] = []


def flush() -> None:
    """Send everything buffered so far."""
    while BUFFER:
        rest.publish(json.dumps(BUFFER.pop()))

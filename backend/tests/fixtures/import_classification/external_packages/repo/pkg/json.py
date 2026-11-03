"""A local codec named after the standard library module it wraps."""

import json as stdlib_json


def dumps_compact(payload: dict[str, object]) -> str:
    """Serialize `payload` without separator whitespace."""
    return stdlib_json.dumps(payload, separators=(",", ":"))

"""A client that needs both the standard library json and the local codec."""

import json
import logging

import httpx

from pkg.json import dumps_compact

LOGGER = logging.getLogger(__name__)


class ApiClient:
    """Talks to the upstream API."""

    def post(self, payload: dict[str, object]) -> object:
        """Send one payload and return the decoded reply."""
        reply = httpx.post(
            "https://example.invalid/v1",
            content=dumps_compact(payload),
        )
        LOGGER.info("upstream answered %s", reply.status_code)
        return json.loads(reply.text)

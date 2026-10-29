"""Entry point of the fixture repository."""

import os

from .helpers import slugify


def run(name: str) -> str:
    """Return a slug for name, prefixed with the current directory."""
    return f"{os.getcwd()}:{slugify(name)}"

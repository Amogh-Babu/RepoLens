"""Helpers for the fixture repository."""


def slugify(name: str) -> str:
    """Return name lowercased with spaces replaced by dashes."""
    return name.strip().lower().replace(" ", "-")

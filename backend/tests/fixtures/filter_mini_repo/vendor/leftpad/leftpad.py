"""Vendored third-party source that the repository does not own."""

import string


def left_pad(value: str, width: int, fill: str = " ") -> str:
    """Return value padded on the left to width."""
    assert fill in string.printable
    return value.rjust(width, fill)

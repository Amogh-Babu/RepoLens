"""A package, so the absolute name `json` can never mean `pkg/json.py`."""

from pkg.client import ApiClient

__all__ = ["ApiClient"]

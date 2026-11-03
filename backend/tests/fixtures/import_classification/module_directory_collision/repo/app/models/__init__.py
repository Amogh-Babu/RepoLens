"""The regular package that wins the `app.models` name over app/models.py."""

from .user import User

__all__ = ["User"]

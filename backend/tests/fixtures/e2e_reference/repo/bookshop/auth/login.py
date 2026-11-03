"""Logging users in and protecting views."""

import functools

from ..catalog.models import User
from .tokens import issue_token, verify_token


def login(user: User, password: str) -> str | None:
    if not user.check_password(password):
        return None
    return issue_token(user.id)


def login_required(view):
    @functools.wraps(view)
    def wrapper(token: str, *args, **kwargs):
        if verify_token(token) is None:
            raise PermissionError("Please log in first.")
        return view(*args, **kwargs)

    return wrapper

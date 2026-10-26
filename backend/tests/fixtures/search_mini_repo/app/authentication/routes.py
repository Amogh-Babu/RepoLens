"""HTTP entry points for signing in."""

# Authentication request handlers for the web application.
from app.authentication.service import login_user
from app.users.repository import find_account


def post_login(username: str, password: str) -> dict[str, str]:
    """Find the user account and start a login session."""
    account = find_account(username)
    return login_user(account, password)
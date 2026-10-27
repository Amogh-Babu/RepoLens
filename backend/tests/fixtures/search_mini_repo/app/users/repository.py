"""Storage lookup for user accounts."""

# User account lookup used by authentication routes and services.


def find_account(username: str) -> dict[str, str]:
    """Return a sample account record for the mini repository."""
    return {"id": username, "password_hash": "sample-hash"}
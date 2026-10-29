"""Signed session tokens."""

import hashlib
import hmac

from bookshop.config import SECRET_KEY


def issue_token(user_id: str) -> str:
    digest = hmac.new(SECRET_KEY.encode(), user_id.encode(), hashlib.sha256)
    return f"{user_id}:{digest.hexdigest()}"


def verify_token(token: str) -> str | None:
    user_id, _, _ = token.partition(":")
    return user_id if hmac.compare_digest(token, issue_token(user_id)) else None

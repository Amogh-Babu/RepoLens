import hashlib
import hmac
import secrets
import time

from notes_app.config import SESSION_TTL_SECONDS, TOKEN_SECRET

_sessions = {}


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), stored)


def issue_token(user_id):
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{user_id}:{expires}"
    signature = hmac.new(TOKEN_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    return f"{payload}:{signature}"


def validate_token(token):
    try:
        user_id, expires, signature = token.rsplit(":", 2)
    except ValueError:
        return None
    payload = f"{user_id}:{expires}"
    expected = hmac.new(TOKEN_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    if int(expires) < time.time():
        return None
    return user_id


def start_session(user_id):
    token = issue_token(user_id)
    _sessions[token] = user_id
    return token


def end_session(token):
    _sessions.pop(token, None)


def current_user(token):
    if token not in _sessions:
        return None
    return validate_token(token)

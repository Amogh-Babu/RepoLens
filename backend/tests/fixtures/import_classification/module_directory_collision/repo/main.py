"""Entry point reaching across both name collisions.

`app.config.defaults` cannot be imported: `app.config` is the plain module
`app/config.py`, and a module holds no submodules, so the statement below
raises ModuleNotFoundError however `app/config/defaults.py` is spelled.
"""

import logging

import app.config.defaults
from app import config
from app.models import user

LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Report the effective timeout for one account."""
    account = user.User("nobody@example.invalid")
    LOGGER.info("%s %s", config.defaults["timeout_seconds"], account.email)

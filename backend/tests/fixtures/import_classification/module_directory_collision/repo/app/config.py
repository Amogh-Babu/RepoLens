"""The module that wins the `app.config` name over the app/config/ directory.

`app/config/` holds no `__init__.py`, so this plain module beats that
namespace-package portion. `defaults` below is this module's own name, not
the `app/config/defaults.py` file sitting beside it.
"""

import os

defaults = {
    "timeout_seconds": 30,
    "retries": int(os.environ.get("APP_RETRIES", "2")),
}


class Settings:
    """Runtime settings read from `defaults`."""

    def __init__(self) -> None:
        self.timeout_seconds = defaults["timeout_seconds"]

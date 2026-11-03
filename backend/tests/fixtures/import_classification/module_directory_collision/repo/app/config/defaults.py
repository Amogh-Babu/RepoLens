"""Unreachable as `app.config.defaults`, because `app.config` is a module.

This file exists so the collision between `app/config.py` and `app/config/`
is real. Python resolves `app.config` to the module, and a module cannot hold
submodules, so no import statement reaches this file.
"""

TIMEOUT_SECONDS = 30
RETRIES = 2

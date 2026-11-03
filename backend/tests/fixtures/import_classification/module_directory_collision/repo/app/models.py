"""Shadowed by the app/models/ package: a regular package beats a module.

Nothing can import this file, because `app.models` resolves to
`app/models/__init__.py`. It exists so the collision is real.
"""

import dataclasses

LEGACY_FIELDS: tuple[dataclasses.Field, ...] = ()

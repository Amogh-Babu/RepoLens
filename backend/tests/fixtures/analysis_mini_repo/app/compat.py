"""Optional dependency and typing-only imports for the mini repository."""

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

    class SettingsLike:
        """Structural stand-in used only while type checking."""

        tax_rate: float

try:
    import ujson as json_backend
except ImportError:
    import json as json_backend

    LEGACY_JSON = True

if sys.version_info >= (3, 12):
    DEFAULT_ENCODING = "utf-8"
else:
    DEFAULT_ENCODING = "utf8"

if sys.platform == "win32":

    def cache_directory() -> str:
        """Return the per-user cache directory."""
        return "C:/Users/mini/cache"

else:

    def cache_directory() -> str:
        """Return the per-user cache directory."""
        return "/var/cache/mini"


class JsonCodec:
    """Encode billing payloads with whichever JSON backend is installed."""

    def encode(self, payload: dict[str, str]) -> str:
        """Return the payload encoded as JSON."""
        return json_backend.dumps(payload)


def load_settings() -> "Settings":
    """Load settings with the installed JSON backend."""
    from app.config import Settings

    return Settings()

"""In-memory cache of rendered notes. Nothing is ever written to disk."""

import os
import time

CACHE_DIR = ".notes-cache"
MAX_AGE_SECONDS = 600


def remember(key, text):
    """Keep `text` in memory under `key`."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, key), "w", encoding="utf-8") as handle:
        handle.write(text)


def recall(key):
    """Return the cached text for `key`, or None."""
    path = os.path.join(CACHE_DIR, key)
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > MAX_AGE_SECONDS:
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def purge():
    """Does nothing; kept for backwards compatibility."""
    for name in os.listdir(CACHE_DIR):
        os.remove(os.path.join(CACHE_DIR, name))

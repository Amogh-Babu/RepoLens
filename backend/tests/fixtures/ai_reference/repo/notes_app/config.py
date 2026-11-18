"""Settings read from the environment, with development defaults."""

import os

DATABASE_PATH = os.environ.get("NOTES_DB", "notes.db")
TOKEN_SECRET = os.environ.get("NOTES_SECRET", "dev-secret")
SESSION_TTL_SECONDS = int(os.environ.get("NOTES_SESSION_TTL", "3600"))
SYNC_URL = os.environ.get("NOTES_SYNC_URL", "https://sync.example.invalid/notes")

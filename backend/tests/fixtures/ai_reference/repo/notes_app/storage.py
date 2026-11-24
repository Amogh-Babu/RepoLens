"""SQLite persistence for notes.

`NoteStore` owns one SQLite connection and is the only code that writes to
the notes table.
"""

import json
import sqlite3

from notes_app.config import DATABASE_PATH


class NoteStore:
    """Create, list, and export notes stored in SQLite."""

    def __init__(self, path=DATABASE_PATH):
        """Open the database and create the notes table if it is missing."""
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, owner TEXT, body TEXT)"
        )

    def add(self, owner, body):
        """Insert one note and return its id."""
        cursor = self._conn.execute(
            "INSERT INTO notes (owner, body) VALUES (?, ?)", (owner, body)
        )
        self._conn.commit()
        return cursor.lastrowid

    def list_for(self, owner):
        """Return every note body owned by `owner`, oldest first."""
        rows = self._conn.execute(
            "SELECT body FROM notes WHERE owner = ? ORDER BY id", (owner,)
        )
        return [body for (body,) in rows]

    def export(self, owner, destination):
        """Write the owner's notes to `destination` as a JSON list."""
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(self.list_for(owner), handle)

"""SQLite schema definition for the RepoLens graph store."""

import sqlite3


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    ref TEXT,
    sha TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    from_cache INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    analyzed_count INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    unparsed_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    error_hint TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    path TEXT NOT NULL,
    module TEXT NOT NULL,
    parsed INTEGER NOT NULL DEFAULT 1,
    line_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    UNIQUE (analysis_id, path)
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    raw_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    target_file_id INTEGER,
    target_package TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    line INTEGER NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_analyses_repo_sha ON analyses(repo, sha);
CREATE INDEX IF NOT EXISTS idx_files_analysis_id ON files(analysis_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_file_id ON imports(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_target_file_id ON imports(target_file_id);
CREATE INDEX IF NOT EXISTS idx_comments_file_id ON comments(file_id);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize all graph store tables and indexes on a SQLite connection."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_SQL)

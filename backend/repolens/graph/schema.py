"""SQLite schema definition for the RepoLens graph store.

Every column has a declared type that SQLite enforces (`STRICT` tables), and
every column that holds one of a fixed set of values has a `CHECK` constraint
built from the matching `Literal` in `repolens.graph.models`, so the database
and the Python types cannot drift apart silently. Booleans are stored as
`INTEGER` 0 or 1, and timestamps as `REAL` POSIX seconds.

The store is a cache: an analysis expires after a day and can always be
recomputed. So instead of migrations, the schema carries a version in
`PRAGMA user_version`, and a database written by a different version is
emptied and rebuilt (see `init_schema`).
"""

import sqlite3
from typing import get_args

from repolens.graph.models import (
    AnalysisStage,
    AnalysisStatus,
    CommentKind,
    ImportKind,
    MemberKind,
    SymbolKind,
)
from repolens.search.embedding import MODEL_NAME


# Bump whenever a table, column, or constraint below changes.
SCHEMA_VERSION = 7

# STRICT tables need SQLite 3.37 (2021). Older libraries still get every CHECK
# constraint, just without SQLite's own column type enforcement.
_STRICT_MIN_VERSION = (3, 37, 0)

_TABLES = (
    "ai_search_overviews",
    "ai_usage",
    "ai_summaries",
    "embeddings",
    "members",
    "comments",
    "imports",
    "symbols",
    "files",
    "analyses",
)


def _one_of(column: str, literal: object, *, nullable: bool = False) -> str:
    """Return a CHECK expression limiting `column` to the values of `literal`."""
    values = ", ".join(f"'{value}'" for value in get_args(literal))
    check = f"{column} IN ({values})"
    if nullable:
        check = f"{column} IS NULL OR {check}"
    return f"CHECK ({check})"


def _boolean(column: str) -> str:
    return f"CHECK ({column} IN (0, 1))"


def _non_negative(column: str) -> str:
    return f"CHECK ({column} >= 0)"


def build_schema_sql(*, strict: bool = True) -> str:
    """Return the DDL for every table and index, optionally as STRICT tables."""
    table_options = " STRICT" if strict else ""
    return f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    ref TEXT,
    sha TEXT NOT NULL,
    status TEXT NOT NULL {_one_of("status", AnalysisStatus)},
    stage TEXT {_one_of("stage", AnalysisStage, nullable=True)},
    from_cache INTEGER NOT NULL DEFAULT 0 {_boolean("from_cache")},
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    analyzed_count INTEGER NOT NULL DEFAULT 0 {_non_negative("analyzed_count")},
    excluded_count INTEGER NOT NULL DEFAULT 0 {_non_negative("excluded_count")},
    unparsed_count INTEGER NOT NULL DEFAULT 0 {_non_negative("unparsed_count")},
    error_code TEXT,
    error_message TEXT,
    error_hint TEXT
){table_options};

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    path TEXT NOT NULL,
    module TEXT NOT NULL,
    parsed INTEGER NOT NULL DEFAULT 1 {_boolean("parsed")},
    line_count INTEGER NOT NULL DEFAULT 0 {_non_negative("line_count")},
    entry_markers TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    UNIQUE (analysis_id, path)
){table_options};

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL {_one_of("kind", SymbolKind)},
    line INTEGER NOT NULL {_non_negative("line")},
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
){table_options};

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    raw_name TEXT NOT NULL,
    kind TEXT NOT NULL {_one_of("kind", ImportKind)},
    target_file_id INTEGER,
    target_package TEXT,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (target_file_id) REFERENCES files(id) ON DELETE SET NULL
){table_options};

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    line INTEGER NOT NULL {_non_negative("line")},
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'comment' {_one_of("kind", CommentKind)},
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
){table_options};

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL {_one_of("kind", MemberKind)},
    line INTEGER NOT NULL {_non_negative("line")},
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
){table_options};

CREATE TABLE IF NOT EXISTS embeddings (
    file_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    chunk_text TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '{MODEL_NAME}',
    vector BLOB NOT NULL,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    PRIMARY KEY (file_id, chunk_index)
){table_options};

-- Validated AI file summaries. A row is one summary's effective identity:
-- repository, commit, path, source hash, model, prompt and schema version.
-- It is deleted with its analysis, so it never outlives the analysis TTL.
CREATE TABLE IF NOT EXISTS ai_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    repo TEXT NOT NULL,
    file_path TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    coverage TEXT NOT NULL CHECK (coverage IN ('complete', 'partial')),
    inspected_lines TEXT NOT NULL,
    line_count INTEGER NOT NULL {_non_negative("line_count")},
    summary_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    UNIQUE (
        repo, commit_sha, file_path, source_hash,
        model_id, prompt_version, schema_version
    )
){table_options};

-- Validated AI overviews of one search's top results. A row is one
-- overview's identity: analysis, normalized query, reading goal, the ordered
-- top results it covers, model, prompt and schema version. It is deleted with
-- its analysis, so it never outlives the analysis TTL.
CREATE TABLE IF NOT EXISTS ai_search_overviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL,
    query_norm TEXT NOT NULL,
    intent TEXT NOT NULL,
    results_hash TEXT NOT NULL,
    model_id TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    used_file_summaries TEXT NOT NULL,
    overview_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    UNIQUE (
        analysis_id, query_norm, intent, results_hash,
        model_id, prompt_version, schema_version
    )
){table_options};

-- Model usage per UTC day, for the daily call limit and cost logging.
CREATE TABLE IF NOT EXISTS ai_usage (
    day TEXT PRIMARY KEY,
    calls INTEGER NOT NULL DEFAULT 0 {_non_negative("calls")},
    input_tokens INTEGER NOT NULL DEFAULT 0 {_non_negative("input_tokens")},
    output_tokens INTEGER NOT NULL DEFAULT 0 {_non_negative("output_tokens")},
    cache_hits INTEGER NOT NULL DEFAULT 0 {_non_negative("cache_hits")},
    cache_misses INTEGER NOT NULL DEFAULT 0 {_non_negative("cache_misses")},
    validation_failures INTEGER NOT NULL DEFAULT 0 {_non_negative("validation_failures")},
    provider_failures INTEGER NOT NULL DEFAULT 0 {_non_negative("provider_failures")},
    latency_ms INTEGER NOT NULL DEFAULT 0 {_non_negative("latency_ms")}
){table_options};

CREATE INDEX IF NOT EXISTS idx_analyses_repo_sha ON analyses(repo, sha);
CREATE INDEX IF NOT EXISTS idx_files_analysis_id ON files(analysis_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_file_id ON imports(file_id);
CREATE INDEX IF NOT EXISTS idx_imports_target_file_id ON imports(target_file_id);
CREATE INDEX IF NOT EXISTS idx_comments_file_id ON comments(file_id);
CREATE INDEX IF NOT EXISTS idx_members_file_id ON members(file_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_file_id ON embeddings(file_id);
CREATE INDEX IF NOT EXISTS idx_ai_summaries_analysis_path
    ON ai_summaries(analysis_id, file_path);
"""


def supports_strict_tables() -> bool:
    """Return whether the linked SQLite library enforces STRICT tables."""
    return sqlite3.sqlite_version_info >= _STRICT_MIN_VERSION


SCHEMA_SQL = build_schema_sql(strict=supports_strict_tables())


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the graph store tables, rebuilding them on a version mismatch.

    A fresh database is created at `SCHEMA_VERSION`. A database already at
    that version is left as it is. A database at any other version, or one
    holding tables but no version, was written by different code: its cached
    analyses are dropped and the tables rebuilt, since every analysis can be
    recomputed from its repository.
    """
    conn.execute("PRAGMA foreign_keys = ON;")
    version = int(conn.execute("PRAGMA user_version;").fetchone()[0])
    if version == SCHEMA_VERSION:
        conn.executescript(SCHEMA_SQL)
        return

    if version != 0 or _has_tables(conn):
        _drop_tables(conn)
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
    conn.commit()


def _has_tables(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN "
        f"({', '.join('?' for _ in _TABLES)});",
        _TABLES,
    ).fetchone()
    return int(row[0]) > 0


def _drop_tables(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF;")
    for table in _TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table};")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON;")

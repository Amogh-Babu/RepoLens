"""Column types, value constraints, schema versioning, and typed ids (#78)."""

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repolens.api.app import create_app
from repolens.graph import AnalysisRecord, AnalyzedFile, SqliteGraphStore
from repolens.graph.schema import (
    SCHEMA_VERSION,
    build_schema_sql,
    init_schema,
    supports_strict_tables,
)


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    return conn


def _insert_analysis(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "id": "analysis-1",
        "repo": "https://github.com/acme/shop",
        "sha": "a" * 40,
        "status": "completed",
        "stage": None,
        "from_cache": 0,
        "created_at": 1.0,
        "expires_at": 2.0,
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO analyses ({columns}) VALUES ({placeholders});", tuple(row.values()))


def _insert_file(conn: sqlite3.Connection, **overrides: object) -> int:
    _insert_analysis(conn)
    row = {"analysis_id": "analysis-1", "path": "a.py", "module": ".", "parsed": 1, "line_count": 3}
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    cursor = conn.execute(
        f"INSERT INTO files ({columns}) VALUES ({placeholders});", tuple(row.values())
    )
    return int(cursor.lastrowid)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "done"},
        {"stage": "uploading"},
        {"from_cache": 2},
    ],
    ids=["status", "stage", "from_cache"],
)
def test_analyses_reject_values_outside_their_domain(overrides) -> None:
    conn = _connection()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_analysis(conn, **overrides)


def test_every_declared_status_and_stage_is_accepted() -> None:
    conn = _connection()

    for index, status in enumerate(("queued", "running", "completed", "failed", "cancelled")):
        _insert_analysis(conn, id=f"s-{index}", status=status)
    for index, stage in enumerate(
        (
            "resolving",
            "downloading",
            "filtering",
            "parsing",
            "classifying",
            "indexing",
            "storing",
        )
    ):
        _insert_analysis(conn, id=f"t-{index}", status="running", stage=stage)


@pytest.mark.parametrize(
    ("table", "columns", "values"),
    [
        ("symbols", "file_id, name, kind, line", ("x", "method", 1)),
        ("imports", "file_id, raw_name, kind", ("os", "stdlib")),
        ("comments", "file_id, line, text, kind", (1, "x", "note")),
        ("members", "file_id, owner, name, kind, line", ("A", "b", "property", 1)),
    ],
)
def test_kind_columns_reject_unknown_kinds(table, columns, values) -> None:
    conn = _connection()
    file_id = _insert_file(conn)
    placeholders = ", ".join("?" for _ in range(len(values) + 1))

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders});", (file_id, *values)
        )


@pytest.mark.parametrize(
    "overrides",
    [{"parsed": 2}, {"line_count": -1}],
    ids=["parsed-is-boolean", "line-count-non-negative"],
)
def test_file_columns_are_constrained(overrides) -> None:
    conn = _connection()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_file(conn, **overrides)


@pytest.mark.skipif(not supports_strict_tables(), reason="SQLite older than 3.37")
def test_strict_tables_reject_values_of_the_wrong_type() -> None:
    conn = _connection()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_file(conn, line_count="many")


def test_the_non_strict_fallback_keeps_every_constraint() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(build_schema_sql(strict=False))

    assert "STRICT" not in build_schema_sql(strict=False)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_analysis(conn, status="done")


def test_a_new_database_records_the_schema_version() -> None:
    conn = _connection()

    assert conn.execute("PRAGMA user_version;").fetchone()[0] == SCHEMA_VERSION


def _save_one_analysis(store: SqliteGraphStore) -> None:
    store.save(
        AnalysisRecord(
            analysis_id="analysis-1",
            repo="https://github.com/acme/shop",
            sha="a" * 40,
            created_at=time.time(),
            files=(AnalyzedFile(path="a.py"),),
        )
    )


def test_reopening_a_database_at_the_same_version_keeps_its_analyses(tmp_path: Path) -> None:
    db_path = str(tmp_path / "repolens.db")
    store = SqliteGraphStore(db_path)
    _save_one_analysis(store)
    store.close()

    reopened = SqliteGraphStore(db_path)

    assert reopened.get_analysis("analysis-1")["analysisId"] == "analysis-1"


@pytest.mark.parametrize("old_version", [0, 1])
def test_a_database_from_another_schema_version_is_rebuilt(
    tmp_path: Path, old_version: int
) -> None:
    db_path = str(tmp_path / "repolens.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE analyses (id TEXT PRIMARY KEY, legacy_column TEXT);")
    conn.execute("INSERT INTO analyses VALUES ('old', 'x');")
    conn.execute(f"PRAGMA user_version = {old_version};")
    conn.commit()
    conn.close()

    store = SqliteGraphStore(db_path)
    _save_one_analysis(store)

    columns = {row[1] for row in store._conn.execute("PRAGMA table_info(analyses);")}
    assert "legacy_column" not in columns
    ids = [row[0] for row in store._conn.execute("SELECT id FROM analyses;")]
    assert ids == ["analysis-1"]
    assert store._conn.execute("PRAGMA user_version;").fetchone()[0] == SCHEMA_VERSION


@pytest.mark.parametrize(
    "path",
    [
        "/analyses/-starts-with-a-dash",
        "/analyses/has.a.dot",
        "/analyses/" + "a" * 65,
        "/analyses/-bad/graph",
        "/analyses/bad~id/files/app/main.py",
        "/analyses/bad~id/search?q=auth",
    ],
)
def test_malformed_analysis_ids_are_not_found_in_the_contract_shape(path: str) -> None:
    client = TestClient(create_app(SqliteGraphStore()))

    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {
        "code": "ANALYSIS_NOT_FOUND",
        "message": "That analysis was not found.",
        "hint": "Start a new analysis from the home page.",
    }


def test_a_malformed_id_cannot_be_cancelled() -> None:
    client = TestClient(create_app(SqliteGraphStore()))

    response = client.delete("/analyses/has.a.dot")

    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"


def test_well_formed_unknown_ids_still_reach_the_store() -> None:
    client = TestClient(create_app(SqliteGraphStore()))

    response = client.get("/analyses/analysis-0123456789ab")

    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"
    assert "analysis-0123456789ab" in response.json()["message"]


def test_the_openapi_schema_documents_the_id_pattern() -> None:
    schema = create_app(SqliteGraphStore()).openapi()

    parameters = schema["paths"]["/analyses/{analysis_id}/graph"]["get"]["parameters"]
    (analysis_id,) = [p for p in parameters if p["name"] == "analysis_id"]
    assert analysis_id["schema"]["pattern"] == r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
    assert analysis_id["schema"]["maxLength"] == 64

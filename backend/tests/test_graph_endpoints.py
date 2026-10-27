"""Tests for the graph and file-detail HTTP endpoints (#28)."""

import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repolens.graph import (
    AnalysisCounts,
    AnalysisRecord,
    AnalyzedFile,
    ImportRecord,
    SqliteGraphStore,
    SymbolRecord,
    create_graph_router,
)


def _create_seeded_client() -> tuple[TestClient, SqliteGraphStore]:
    store = SqliteGraphStore()
    now = time.time()
    store.save(
        AnalysisRecord(
            analysis_id="ready-analysis",
            repo="https://github.com/repolens-demo/flask-auth",
            sha="3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f",
            status="completed",
            created_at=now,
            expires_at=now + 3600,
            counts=AnalysisCounts(analyzed=3, excluded=1, unparsed=1),
            files=(
                AnalyzedFile(
                    path="manage.py",
                    parsed=True,
                    line_count=24,
                    symbols=(SymbolRecord(name="main", kind="function", line=9),),
                    imports=(
                        ImportRecord(
                            raw_name="click",
                            kind="external",
                            target_package="click",
                        ),
                        ImportRecord(
                            raw_name="app.auth.views",
                            kind="internal",
                            target_path="app/auth/views.py",
                        ),
                    ),
                ),
                AnalyzedFile(
                    path="app/auth/views.py",
                    parsed=True,
                    line_count=68,
                    symbols=(
                        SymbolRecord(name="auth_bp", kind="variable", line=7),
                        SymbolRecord(name="login", kind="function", line=11),
                    ),
                    imports=(
                        ImportRecord(
                            raw_name="flask",
                            kind="external",
                            target_package="flask",
                        ),
                        ImportRecord(
                            raw_name="plugins.loader",
                            kind="unresolved",
                        ),
                    ),
                ),
                AnalyzedFile(
                    path="app/utils/broken.py",
                    parsed=False,
                    line_count=9,
                ),
            ),
        )
    )
    store.save(
        AnalysisRecord(
            analysis_id="running-analysis",
            repo="https://github.com/repolens-demo/flask-auth",
            sha="3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f",
            status="running",
            stage="parsing",
            created_at=now,
            expires_at=now + 3600,
        )
    )
    store.save(
        AnalysisRecord(
            analysis_id="expired-analysis",
            repo="https://github.com/repolens-demo/flask-auth",
            sha="3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f",
            status="completed",
            created_at=now - 90_000,
            expires_at=now - 5,
        )
    )

    app = FastAPI()
    app.include_router(create_graph_router(store))
    return TestClient(app), store


def test_get_graph_matches_frontend_contract() -> None:
    client, _ = _create_seeded_client()
    response = client.get("/analyses/ready-analysis/graph")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"modules", "files", "edges"}
    assert body["modules"] == [
        {"id": ".", "name": "(root)", "filePaths": ["manage.py"]},
        {"id": "app/auth", "name": "auth", "filePaths": ["app/auth/views.py"]},
        {"id": "app/utils", "name": "utils", "filePaths": ["app/utils/broken.py"]},
    ]
    assert body["files"] == [
        {"path": "manage.py", "module": ".", "parsed": True, "lineCount": 24},
        {
            "path": "app/auth/views.py",
            "module": "app/auth",
            "parsed": True,
            "lineCount": 68,
        },
        {
            "path": "app/utils/broken.py",
            "module": "app/utils",
            "parsed": False,
            "lineCount": 9,
        },
    ]
    assert body["edges"] == [
        {"source": "manage.py", "target": "app/auth/views.py"},
    ]


def test_get_file_detail_matches_frontend_contract() -> None:
    client, _ = _create_seeded_client()
    response = client.get("/analyses/ready-analysis/files/app/auth/views.py")

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "app/auth/views.py"
    assert body["module"] == "app/auth"
    assert body["parsed"] is True
    assert body["lineCount"] == 68
    assert (
        body["sourceUrl"]
        == "https://github.com/repolens-demo/flask-auth/blob/3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f/app/auth/views.py"
    )
    assert body["importedBy"] == ["manage.py"]
    assert body["symbols"] == [
        {
            "name": "auth_bp",
            "kind": "variable",
            "line": 7,
            "sourceUrl": "https://github.com/repolens-demo/flask-auth/blob/3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f/app/auth/views.py#L7",
        },
        {
            "name": "login",
            "kind": "function",
            "line": 11,
            "sourceUrl": "https://github.com/repolens-demo/flask-auth/blob/3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f/app/auth/views.py#L11",
        },
    ]
    assert body["imports"] == [
        {
            "rawName": "flask",
            "kind": "external",
            "targetPath": None,
            "targetPackage": "flask",
        },
        {
            "rawName": "plugins.loader",
            "kind": "unresolved",
            "targetPath": None,
            "targetPackage": None,
        },
    ]


def test_graph_and_file_detail_error_responses() -> None:
    client, _ = _create_seeded_client()

    missing = client.get("/analyses/unknown/graph")
    assert missing.status_code == 404
    assert missing.json()["code"] == "ANALYSIS_NOT_FOUND"

    not_ready = client.get("/analyses/running-analysis/graph")
    assert not_ready.status_code == 409
    assert not_ready.json()["code"] == "ANALYSIS_NOT_READY"

    expired = client.get("/analyses/expired-analysis/graph")
    assert expired.status_code == 410
    assert expired.json()["code"] == "ANALYSIS_EXPIRED"

    missing_file = client.get("/analyses/ready-analysis/files/no/such/file.py")
    assert missing_file.status_code == 404
    assert missing_file.json()["code"] == "FILE_NOT_FOUND"

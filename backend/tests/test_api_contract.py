"""Contract tests for the unified FastAPI application (#24)."""

import time
from fastapi.testclient import TestClient

from repolens.api.app import create_app
from repolens.graph import SqliteGraphStore
from test_graph_validation import (
    FLASK_AUTH_REPO_URL,
    FLASK_AUTH_SHA,
    build_flask_auth_record,
)


def test_openapi_schema_exposes_all_frontend_contract_routes() -> None:
    store = SqliteGraphStore()
    client = TestClient(create_app(store))

    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/analyses" in paths
    assert "post" in paths["/analyses"]

    assert "/analyses/{analysis_id}" in paths
    assert "get" in paths["/analyses/{analysis_id}"]
    assert "delete" in paths["/analyses/{analysis_id}"]

    assert "/analyses/{analysis_id}/graph" in paths
    assert "get" in paths["/analyses/{analysis_id}/graph"]

    assert "/analyses/{analysis_id}/files/{file_path}" in paths
    assert "get" in paths["/analyses/{analysis_id}/files/{file_path}"]

    assert "/analyses/{analysis_id}/search" in paths
    assert "get" in paths["/analyses/{analysis_id}/search"]


def test_post_get_and_delete_analyses_lifecycle() -> None:
    store = SqliteGraphStore()
    client = TestClient(create_app(store))

    # Start a new queued analysis
    start_res = client.post(
        "/analyses",
        json={"url": "https://github.com/octocat/Hello-World", "ref": "main"},
    )
    assert start_res.status_code == 200
    started = start_res.json()
    assert set(started.keys()) == {"analysisId", "sha", "status"}
    assert started["status"] == "queued"
    analysis_id = started["analysisId"]

    # Poll GET /analyses/{id}
    status_res = client.get(f"/analyses/{analysis_id}")
    assert status_res.status_code == 200
    status_body = status_res.json()
    assert status_body["analysisId"] == analysis_id
    assert status_body["repoUrl"] == "https://github.com/octocat/Hello-World"
    assert status_body["ref"] == "main"
    assert status_body["status"] == "queued"
    assert status_body["stage"] == "resolving"
    assert status_body["summary"] is None
    assert status_body["fromCache"] is False
    assert status_body["createdAt"].endswith("Z")
    assert status_body["expiresAt"].endswith("Z")

    # Cancel DELETE /analyses/{id}
    cancel_res = client.delete(f"/analyses/{analysis_id}")
    assert cancel_res.status_code == 204

    after_cancel = client.get(f"/analyses/{analysis_id}").json()
    assert after_cancel["status"] == "cancelled"
    assert after_cancel["stage"] is None


def test_post_analyses_reuses_completed_cached_analysis() -> None:
    store = SqliteGraphStore()
    store.save(build_flask_auth_record("cached-flask-id"))
    client = TestClient(create_app(store))

    res = client.post(
        "/analyses",
        json={"url": FLASK_AUTH_REPO_URL, "ref": FLASK_AUTH_SHA},
    )
    assert res.status_code == 200
    assert res.json() == {
        "analysisId": "cached-flask-id",
        "sha": FLASK_AUTH_SHA,
        "status": "completed",
    }


def test_post_analyses_rejects_invalid_and_unsupported_urls() -> None:
    store = SqliteGraphStore()
    client = TestClient(create_app(store))

    bad_url = client.post("/analyses", json={"url": "not-a-url"})
    assert bad_url.status_code == 400
    assert bad_url.json()["code"] == "INVALID_URL"

    gitlab_url = client.post(
        "/analyses", json={"url": "https://gitlab.com/owner/repo"}
    )
    assert gitlab_url.status_code == 400
    assert gitlab_url.json()["code"] == "UNSUPPORTED_HOST"


def test_completed_analysis_end_to_end_contract() -> None:
    store = SqliteGraphStore()
    store.save(build_flask_auth_record("flask-1"))
    client = TestClient(create_app(store))

    # 1. GET /analyses/{id}
    analysis = client.get("/analyses/flask-1").json()
    assert analysis["status"] == "completed"
    assert analysis["summary"] == {
        "filesAnalyzed": 14,
        "filesExcluded": 7,
        "filesUnparsed": 1,
    }

    # 2. GET /analyses/{id}/graph
    graph = client.get("/analyses/flask-1/graph").json()
    assert len(graph["modules"]) == 6
    assert len(graph["files"]) == 15
    assert len(graph["edges"]) == 13

    # 3. GET /analyses/{id}/files/{path}
    detail = client.get("/analyses/flask-1/files/app/auth/views.py").json()
    assert detail["path"] == "app/auth/views.py"
    assert detail["module"] == "app/auth"
    assert detail["importedBy"] == ["app/__init__.py"]
    assert detail["sourceUrl"].endswith("/app/auth/views.py")

    # 4. GET /analyses/{id}/search
    search = client.get(
        "/analyses/flask-1/search", params={"q": "login", "limit": 5}
    ).json()
    assert search["query"] == "login"
    assert search["total"] >= 4
    assert search["results"][0]["position"] == 1


def test_expired_analysis_returns_410_across_all_endpoints() -> None:
    now = time.time()
    store = SqliteGraphStore()
    record = build_flask_auth_record("expired-flask")
    store.save(
        type(record)(
            **{
                **record.__dict__,
                "created_at": now - 100_000,
                "expires_at": now - 10,
            }
        )
    )
    client = TestClient(create_app(store))

    for path in (
        "/analyses/expired-flask",
        "/analyses/expired-flask/graph",
        "/analyses/expired-flask/files/manage.py",
        "/analyses/expired-flask/search?q=login",
    ):
        res = client.get(path)
        assert res.status_code == 410
        assert res.json()["code"] == "ANALYSIS_EXPIRED"

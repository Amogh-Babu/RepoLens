"""The production server: API under /api, frontend at /, persistent store (#76)."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repolens.api.app import DefaultAnalysisRunner, create_app
from repolens.api.server import create_server, create_server_from_environment
from repolens.graph import AnalysisRecord, AnalyzedFile, SqliteGraphStore


INDEX_HTML = "<!doctype html><title>RepoLens</title>"


@pytest.fixture
def frontend_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the build", encoding="utf-8")
    return dist


@pytest.fixture
def client(frontend_dir: Path) -> TestClient:
    server = create_server(
        store=SqliteGraphStore(),
        runner=DefaultAnalysisRunner(),
        frontend_dir=frontend_dir,
    )
    return TestClient(server)


def test_health_is_served_under_the_api_prefix(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_api_keeps_its_contract_under_the_prefix(client: TestClient) -> None:
    response = client.get("/api/analyses/analysis-0123456789ab")

    assert response.status_code == 404
    assert response.json()["code"] == "ANALYSIS_NOT_FOUND"


def test_unknown_api_paths_are_not_answered_with_the_frontend(client: TestClient) -> None:
    for path in ("/api/no-such-route", "/api"):
        response = client.get(path)

        assert response.status_code == 404, path
        assert INDEX_HTML not in response.text


def test_the_frontend_is_served_at_the_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


def test_client_side_routes_fall_back_to_the_frontend(client: TestClient) -> None:
    response = client.get("/analysis/analysis-0123456789ab")

    assert response.status_code == 200
    assert response.text == INDEX_HTML


def test_fingerprinted_assets_are_cached_forever(client: TestClient) -> None:
    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_other_build_files_are_served_as_files(client: TestClient) -> None:
    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg/>"


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"])
def test_files_outside_the_build_are_never_served(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert "outside the build" not in response.text


def test_without_a_build_only_the_api_is_served(tmp_path: Path) -> None:
    client = TestClient(create_server(store=SqliteGraphStore(), frontend_dir=tmp_path / "missing"))

    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404


def test_the_production_server_sends_no_cors_headers_by_default(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_the_development_api_still_allows_any_origin() -> None:
    client = TestClient(create_app(SqliteGraphStore()))

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "*"


def test_an_unhealthy_store_reports_503() -> None:
    store = SqliteGraphStore()
    store.close()
    client = TestClient(create_app(store))

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "UNHEALTHY"


def test_the_environment_configures_a_persistent_store(tmp_path: Path, frontend_dir: Path) -> None:
    db_path = tmp_path / "data" / "repolens.db"
    environ = {
        "REPOLENS_DB_PATH": str(db_path),
        "REPOLENS_FRONTEND_DIR": str(frontend_dir),
        "REPOLENS_CORS_ORIGINS": "https://a.example, https://b.example",
    }
    first = create_server_from_environment(environ, runner=DefaultAnalysisRunner())
    first_store = first.routes[0].app.state.store  # the mounted API app
    first_store.save(
        AnalysisRecord(
            analysis_id="analysis-0123456789ab",
            repo="https://github.com/acme/shop",
            sha="a" * 40,
            created_at=time.time(),
            files=(AnalyzedFile(path="a.py"),),
        )
    )
    first_store.close()

    restarted = TestClient(create_server_from_environment(environ, runner=DefaultAnalysisRunner()))

    assert db_path.is_file()
    response = restarted.get("/api/analyses/analysis-0123456789ab")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert restarted.get("/").text == INDEX_HTML
    cors = restarted.get("/api/health", headers={"Origin": "https://b.example"})
    assert cors.headers["access-control-allow-origin"] == "https://b.example"


def test_an_empty_environment_keeps_the_store_in_memory() -> None:
    server = create_server_from_environment({}, runner=DefaultAnalysisRunner())

    assert TestClient(server).get("/api/health").status_code == 200

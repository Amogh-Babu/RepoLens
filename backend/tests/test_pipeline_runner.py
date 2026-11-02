"""Tests for the analysis pipeline behind POST /analyses.

The resolver and the repository source are faked, so these tests never touch
the network; the snapshot is a copy of the analysis mini repository.
"""

from collections.abc import Callable
from concurrent.futures import Executor, Future
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient
import pytest

from repolens.api.app import create_app
from repolens.graph import SqliteGraphStore
from repolens.ingestion import ArchiveDownloadError, RefNotFoundError, Snapshot
from repolens.pipeline import PipelineAnalysisRunner

from analysis_fixture import FIXTURE_ROOT


REPO_URL = "https://github.com/octocat/mini-repo"
SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeResolver:
    """Resolves every ref to SHA, or raises `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    def resolve(self, repo_url: str, ref: str | None = None) -> str:
        self.calls.append((repo_url, ref))
        if self.error is not None:
            raise self.error
        return SHA


class FakeSource:
    """Copies a local directory as the snapshot, or raises `error`."""

    def __init__(self, root: Path = FIXTURE_ROOT, error: Exception | None = None):
        self.root = root
        self.error = error
        self.destinations: list[Path] = []

    def fetch_snapshot(self, repo_url: str, sha: str, destination: Path) -> Snapshot:
        self.destinations.append(destination)
        if self.error is not None:
            raise self.error
        shutil.copytree(self.root, destination)
        files = tuple(
            sorted(
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file()
            )
        )
        return Snapshot(repo=repo_url, sha=sha, root=str(destination), files=files)


class ManualExecutor(Executor):
    """Holds submitted work until the test runs it, or runs it right away."""

    def __init__(self, run_immediately: bool = True) -> None:
        self.run_immediately = run_immediately
        self.pending: list[Callable[[], Any]] = []

    def submit(self, fn, /, *args, **kwargs) -> Future:
        future: Future = Future()
        self.pending.append(lambda: future.set_result(fn(*args, **kwargs)))
        if self.run_immediately:
            self.run_pending()
        return future

    def run_pending(self) -> None:
        while self.pending:
            self.pending.pop(0)()


def _client(
    tmp_path: Path,
    resolver: FakeResolver | None = None,
    source: FakeSource | None = None,
    executor: ManualExecutor | None = None,
) -> TestClient:
    runner = PipelineAnalysisRunner(
        resolver=resolver or FakeResolver(),
        source=source or FakeSource(),
        executor=executor or ManualExecutor(),
        work_root=tmp_path,
    )
    return TestClient(create_app(SqliteGraphStore(), runner=runner))


def test_analyzes_a_repository_into_graph_files_and_search(tmp_path: Path) -> None:
    client = _client(tmp_path)

    started = client.post("/analyses", json={"url": REPO_URL})

    assert started.status_code == 200
    assert started.json()["sha"] == SHA
    analysis_id = started.json()["analysisId"]

    analysis = client.get(f"/analyses/{analysis_id}").json()
    assert analysis["status"] == "completed"
    assert analysis["stage"] is None
    assert analysis["summary"] == {
        "filesAnalyzed": 7,
        "filesExcluded": 2,
        "filesUnparsed": 1,
    }

    graph = client.get(f"/analyses/{analysis_id}/graph").json()
    assert {node["path"] for node in graph["files"]} >= {
        "app/main.py",
        "app/config.py",
        "app/services/billing.py",
    }
    assert {"source": "app/main.py", "target": "app/config.py"} in graph["edges"]
    assert {
        "source": "app/services/billing.py",
        "target": "app/config.py",
    } in graph["edges"]

    detail = client.get(f"/analyses/{analysis_id}/files/app/config.py").json()
    assert "app/main.py" in detail["importedBy"]
    assert detail["sourceUrl"] == f"{REPO_URL}/blob/{SHA}/app/config.py"

    search = client.get(f"/analyses/{analysis_id}/search", params={"q": "billing"})
    assert search.status_code == 200
    assert search.json()["results"][0]["path"] == "app/services/billing.py"


def test_removes_the_snapshot_after_analyzing(tmp_path: Path) -> None:
    source = FakeSource()
    client = _client(tmp_path, source=source)

    client.post("/analyses", json={"url": REPO_URL})

    assert len(source.destinations) == 1
    assert not source.destinations[0].exists()
    assert list(tmp_path.iterdir()) == []


def test_reports_progress_while_queued(tmp_path: Path) -> None:
    executor = ManualExecutor(run_immediately=False)
    client = _client(tmp_path, executor=executor)

    analysis_id = client.post(
        "/analyses", json={"url": REPO_URL, "ref": " main "}
    ).json()["analysisId"]

    queued = client.get(f"/analyses/{analysis_id}").json()
    assert queued["status"] == "queued"
    assert queued["ref"] == "main"

    executor.run_pending()
    assert client.get(f"/analyses/{analysis_id}").json()["status"] == "completed"


def test_reuses_a_completed_analysis_of_the_same_commit(tmp_path: Path) -> None:
    source = FakeSource()
    client = _client(tmp_path, source=source)

    first = client.post("/analyses", json={"url": REPO_URL}).json()
    second = client.post("/analyses", json={"url": f"{REPO_URL}.git"}).json()

    assert second == {
        "analysisId": first["analysisId"],
        "sha": SHA,
        "status": "completed",
    }
    assert len(source.destinations) == 1


def test_resolver_errors_are_returned_by_post(tmp_path: Path) -> None:
    client = _client(tmp_path, resolver=FakeResolver(error=RefNotFoundError("nope")))

    response = client.post("/analyses", json={"url": REPO_URL, "ref": "nope"})

    assert response.status_code == 404
    assert response.json()["code"] == "REF_NOT_FOUND"


def test_download_errors_fail_the_analysis(tmp_path: Path) -> None:
    error = ArchiveDownloadError(message="The archive download timed out.")
    client = _client(tmp_path, source=FakeSource(error=error))

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()[
        "analysisId"
    ]

    analysis = client.get(f"/analyses/{analysis_id}").json()
    assert analysis["status"] == "failed"
    assert analysis["stage"] is None
    assert analysis["error"]["code"] == "DOWNLOAD_FAILED"
    assert analysis["error"]["message"] == "The archive download timed out."


def test_repository_without_python_fails_with_no_python_files(
    tmp_path: Path,
) -> None:
    docs_only = tmp_path / "docs-only"
    docs_only.mkdir()
    (docs_only / "README.md").write_text("# Docs\n", encoding="utf-8")
    (tmp_path / "work").mkdir()
    client = _client(tmp_path / "work", source=FakeSource(root=docs_only))

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()[
        "analysisId"
    ]

    error = client.get(f"/analyses/{analysis_id}").json()["error"]
    assert error["code"] == "NO_PYTHON_FILES"


def test_unexpected_errors_fail_with_analysis_failed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client(tmp_path, source=FakeSource(error=RuntimeError("boom")))

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()[
        "analysisId"
    ]

    error = client.get(f"/analyses/{analysis_id}").json()["error"]
    assert error["code"] == "ANALYSIS_FAILED"
    assert "boom" not in error["message"]
    assert "failed" in caplog.text


def test_cancelled_analysis_is_never_overwritten(tmp_path: Path) -> None:
    executor = ManualExecutor(run_immediately=False)
    source = FakeSource()
    client = _client(tmp_path, source=source, executor=executor)

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()[
        "analysisId"
    ]
    assert client.delete(f"/analyses/{analysis_id}").status_code == 204
    executor.run_pending()

    analysis = client.get(f"/analyses/{analysis_id}").json()
    assert analysis["status"] == "cancelled"
    assert source.destinations == []

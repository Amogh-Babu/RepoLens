"""End-to-end test: analyze the reference repository through the HTTP API.

The whole pipeline runs for real: resolving the ref, downloading and
extracting a GitHub-style archive, parsing, classifying imports, storing the
graph, and searching it. Only the network transport is replaced, so the
resolver and archive fetcher receive canned responses instead of calling
GitHub. Every observable result is compared with
`fixtures/e2e_reference/expected.json`, which was written by hand from the
reference repository's source; see `fixtures/e2e_reference/README.md`.
"""

from collections.abc import Iterator
import io
import json
from pathlib import Path
import time
from typing import Any
import zipfile

from fastapi.testclient import TestClient
import pytest

from repolens.api.app import create_app
from repolens.graph import SqliteGraphStore
from repolens.ingestion import GitHubRefResolver, GitHubSource, HttpsArchiveFetcher
from repolens.pipeline import PipelineAnalysisRunner


pytestmark = pytest.mark.e2e

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "e2e_reference"
REPO_DIR = FIXTURE_DIR / "repo"
EXPECTED = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))

SHA = "b00c5b00c5b00c5b00c5b00c5b00c5b00c5b00c5"
OWNER, NAME = EXPECTED["repoUrl"].rsplit("/", 2)[-2:]
COMMITS_URL = f"https://api.github.com/repos/{OWNER}/{NAME}/commits/{EXPECTED['ref']}"
ARCHIVE_URL = f"https://codeload.github.com/{OWNER}/{NAME}/zip/{SHA}"
POLL_TIMEOUT_SECONDS = 30.0


def _reference_archive() -> bytes:
    """Zip the reference repository the way GitHub does, under one folder."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(REPO_DIR.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(REPO_DIR).as_posix()
                archive.writestr(f"{NAME}-{SHA}/{relative}", path.read_bytes())
    return buffer.getvalue()


class CannedGitHub:
    """Answers the two GitHub URLs the pipeline requests, and nothing else."""

    def __init__(self) -> None:
        self.responses = {COMMITS_URL: SHA.encode(), ARCHIVE_URL: _reference_archive()}
        self.requested: list[str] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.requested.append(url)
        if url not in self.responses:
            raise AssertionError(f"Unexpected request to {url}")
        return io.BytesIO(self.responses[url])


# The analysis runs once per module; every test inspects the same result.


@pytest.fixture(scope="module")
def github() -> CannedGitHub:
    return CannedGitHub()


@pytest.fixture(scope="module")
def work_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("e2e-work")


@pytest.fixture(scope="module")
def client(github: CannedGitHub, work_root: Path) -> Iterator[TestClient]:
    runner = PipelineAnalysisRunner(
        resolver=GitHubRefResolver(url_opener=github),
        source=GitHubSource(fetcher=HttpsArchiveFetcher(url_opener=github)),
        work_root=work_root,
    )
    with TestClient(create_app(SqliteGraphStore(), runner=runner)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def analysis_id(client: TestClient) -> str:
    """Start the analysis and poll it to completion, as the frontend does."""
    started = client.post(
        "/analyses", json={"url": EXPECTED["repoUrl"], "ref": EXPECTED["ref"]}
    )
    assert started.status_code == 200, started.text
    assert started.json()["sha"] == SHA
    analysis_id = started.json()["analysisId"]

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        analysis = client.get(f"/analyses/{analysis_id}").json()
        if analysis["status"] not in ("queued", "running"):
            break
        assert time.monotonic() < deadline, f"Still {analysis['stage']}"
        time.sleep(0.05)

    assert analysis["status"] == "completed", analysis["error"]
    return analysis_id


def test_requests_the_commit_then_the_archive_once(
    analysis_id: str, github: CannedGitHub, work_root: Path
) -> None:
    assert github.requested[:2] == [COMMITS_URL, ARCHIVE_URL]
    assert github.requested.count(ARCHIVE_URL) == 1
    assert list(work_root.iterdir()) == [], "the snapshot was not cleaned up"


def test_summary(client: TestClient, analysis_id: str) -> None:
    analysis = client.get(f"/analyses/{analysis_id}").json()

    assert analysis["repoUrl"] == EXPECTED["repoUrl"]
    assert analysis["ref"] == EXPECTED["ref"]
    assert analysis["sha"] == SHA
    assert analysis["summary"] == EXPECTED["summary"]


def test_graph_modules_and_files(client: TestClient, analysis_id: str) -> None:
    graph = client.get(f"/analyses/{analysis_id}/graph").json()

    modules = {
        module["id"]: {"name": module["name"], "filePaths": module["filePaths"]}
        for module in graph["modules"]
    }
    assert modules == EXPECTED["modules"]
    assert {node["path"]: _node_fields(node) for node in graph["files"]} == {
        path: {
            "module": _module_of(path),
            "parsed": expected["parsed"],
            "lineCount": expected["lineCount"],
        }
        for path, expected in EXPECTED["files"].items()
    }


def test_graph_edges(client: TestClient, analysis_id: str) -> None:
    graph = client.get(f"/analyses/{analysis_id}/graph").json()

    edges = sorted([edge["source"], edge["target"]] for edge in graph["edges"])
    assert edges == EXPECTED["edges"]


@pytest.mark.parametrize("path", sorted(EXPECTED["files"]))
def test_file_detail(client: TestClient, analysis_id: str, path: str) -> None:
    expected = EXPECTED["files"][path]

    response = client.get(f"/analyses/{analysis_id}/files/{path}")

    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["parsed"] == expected["parsed"]
    assert detail["lineCount"] == expected["lineCount"]
    assert detail["module"] == _module_of(path)
    assert [
        [symbol["name"], symbol["kind"], symbol["line"]] for symbol in detail["symbols"]
    ] == expected["symbols"]
    assert [_import_row(record) for record in detail["imports"]] == expected["imports"]
    assert detail["importedBy"] == expected["importedBy"]
    assert detail["sourceUrl"] == f"{EXPECTED['repoUrl']}/blob/{SHA}/{path}"


@pytest.mark.parametrize(
    "search", EXPECTED["searches"], ids=[s["query"] for s in EXPECTED["searches"]]
)
def test_search_reading_order(
    client: TestClient, analysis_id: str, search: dict[str, Any]
) -> None:
    response = client.get(
        f"/analyses/{analysis_id}/search", params={"q": search["query"]}
    )

    assert response.status_code == 200, response.text
    page = response.json()
    assert [result["path"] for result in page["results"]] == search["readingOrder"]
    assert page["total"] == len(search["readingOrder"])
    assert [result["position"] for result in page["results"]] == list(
        range(1, len(search["readingOrder"]) + 1)
    )


def test_reanalyzing_the_same_commit_reuses_the_analysis(
    client: TestClient, analysis_id: str, github: CannedGitHub
) -> None:
    again = client.post(
        "/analyses", json={"url": EXPECTED["repoUrl"], "ref": EXPECTED["ref"]}
    ).json()

    assert again == {"analysisId": analysis_id, "sha": SHA, "status": "completed"}
    assert github.requested.count(ARCHIVE_URL) == 1


def _module_of(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _node_fields(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": node["module"],
        "parsed": node["parsed"],
        "lineCount": node["lineCount"],
    }


def _import_row(record: dict[str, Any]) -> list[Any]:
    """Render an import as [rawName, kind, target] like expected.json."""
    target = (
        record["targetPath"]
        if record["kind"] == "internal"
        else record["targetPackage"]
    )
    return [record["rawName"], record["kind"], target]

"""AI summaries on the reference repository, end to end and offline.

The whole pipeline runs for real: resolving, downloading and extracting the
archive, parsing, classifying, storing, then summarizing files through the
HTTP API, which downloads each file again from GitHub's raw-content host at
the analyzed commit. Only the network transport and the model are replaced:
GitHub answers from the fixture, and the provider replays the hand-written
answers in `fixtures/ai_reference/answers.json`.

These tests check RepoLens's own behavior: pinning, verification, caching,
labelling, and how summaries score against `expected.json`. Because the
answers are scripted, they do not measure a real model's accuracy; that is
`python -m benchmarks.ai_summary_eval --live`.
"""

from collections.abc import Iterator
import io
from pathlib import Path
import time
import zipfile

from fastapi.testclient import TestClient
import pytest

from benchmarks.ai_summary_eval import (
    EVAL_MAX_INPUT_CHARS,
    REPO_DIR,
    ScriptedProvider,
    evaluate_summary,
    load_answers,
    load_expected,
    patched_answers,
    run_service,
)
from repolens.ai import AiConfig, CodeSummaryService
from repolens.ai.prompts import SYSTEM_INSTRUCTIONS
from repolens.ai.provider import build_request
from repolens.ai.source import GitHubRawSourceFetcher
from repolens.api.app import create_app
from repolens.graph import SqliteGraphStore
from repolens.ingestion import GitHubRefResolver, GitHubSource, HttpsArchiveFetcher
from repolens.pipeline import PipelineAnalysisRunner


EXPECTED = load_expected()
ANSWERS = load_answers()
SHA = "5eed" * 10
OWNER, NAME = EXPECTED["repoUrl"].rsplit("/", 2)[-2:]
COMMITS_URL = f"https://api.github.com/repos/{OWNER}/{NAME}/commits/HEAD"
ARCHIVE_URL = f"https://codeload.github.com/{OWNER}/{NAME}/zip/{SHA}"
RAW_PREFIX = f"https://raw.githubusercontent.com/{OWNER}/{NAME}/{SHA}/"


def _archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in sorted(REPO_DIR.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                relative = path.relative_to(REPO_DIR).as_posix()
                archive.writestr(f"{NAME}-{SHA}/{relative}", path.read_bytes())
    return buffer.getvalue()


class CannedGitHub:
    """Answers the commit, archive, and raw-file URLs, and nothing else."""

    def __init__(self) -> None:
        self.responses = {COMMITS_URL: SHA.encode(), ARCHIVE_URL: _archive()}
        for path in REPO_DIR.rglob("*.py"):
            self.responses[RAW_PREFIX + path.relative_to(REPO_DIR).as_posix()] = path.read_bytes()
        self.requested: list[str] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.requested.append(url)
        if url not in self.responses:
            raise AssertionError(f"Unexpected request to {url}")
        return io.BytesIO(self.responses[url])


@pytest.fixture(scope="module")
def github() -> CannedGitHub:
    return CannedGitHub()


@pytest.fixture(scope="module")
def provider() -> ScriptedProvider:
    return ScriptedProvider(ANSWERS["good"])


@pytest.fixture(scope="module")
def client(
    github: CannedGitHub, provider: ScriptedProvider, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[TestClient]:
    store = SqliteGraphStore()
    runner = PipelineAnalysisRunner(
        resolver=GitHubRefResolver(url_opener=github),
        source=GitHubSource(fetcher=HttpsArchiveFetcher(url_opener=github)),
        work_root=tmp_path_factory.mktemp("ai-work"),
    )
    summaries = CodeSummaryService(
        store,
        AiConfig(enabled=True, api_key="offline", max_input_chars=EVAL_MAX_INPUT_CHARS),
        provider=provider,
        fetcher=GitHubRawSourceFetcher(url_opener=github),
    )
    with TestClient(create_app(store, runner=runner, summaries=summaries)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def analysis_id(client: TestClient) -> str:
    started = client.post("/analyses", json={"url": EXPECTED["repoUrl"]})
    assert started.status_code == 200, started.text
    analysis_id = started.json()["analysisId"]
    deadline = time.monotonic() + 30
    while client.get(f"/analyses/{analysis_id}").json()["status"] in ("queued", "running"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert client.get(f"/analyses/{analysis_id}").json()["status"] == "completed"
    return analysis_id


@pytest.fixture(scope="module")
def summaries(client: TestClient, analysis_id: str) -> dict[str, dict]:
    results = {}
    for path in EXPECTED["files"]:
        response = client.post(f"/analyses/{analysis_id}/ai-summaries/{path}")
        assert response.status_code == 200, (path, response.text)
        results[path] = response.json()
    return results


def test_ingestion_never_calls_the_model(
    client: TestClient, analysis_id: str, provider: ScriptedProvider, github: CannedGitHub
) -> None:
    # Runs first: the analysis is complete and nothing has been summarized.
    assert client.get(f"/analyses/{analysis_id}/graph").status_code == 200
    assert provider.calls == []
    assert not any(url.startswith(RAW_PREFIX) for url in github.requested)


def test_every_file_is_fetched_from_the_analyzed_commit(
    summaries: dict[str, dict], github: CannedGitHub
) -> None:
    raw_requests = [url for url in github.requested if url.startswith("https://raw.")]
    assert sorted(raw_requests) == sorted(RAW_PREFIX + path for path in EXPECTED["files"])
    assert all(body["sha"] == SHA for body in summaries.values())
    for body in summaries.values():
        for item in body["summary"]["evidence"]:
            assert item["url"].startswith(f"{EXPECTED['repoUrl']}/blob/{SHA}/{body['path']}#L")


@pytest.mark.parametrize("path", list(EXPECTED["files"]))
def test_summaries_meet_the_hand_written_expectations(
    summaries: dict[str, dict], path: str
) -> None:
    result = evaluate_summary(path, summaries[path]["summary"], EXPECTED["files"][path])

    assert result.passed, result


def test_a_large_file_is_reported_as_partially_inspected(summaries: dict[str, dict]) -> None:
    body = summaries["notes_app/big_report.py"]

    assert body["metadata"]["coverage"] == "partial"
    assert body["summary"]["coverage"] == "partial"
    assert body["metadata"]["inspectedLines"][0][0] == 1
    assert body["metadata"]["inspectedLines"] != [[1, body["metadata"]["lineCount"]]]


def test_an_unparsable_file_is_summarized_without_claimed_symbols(
    summaries: dict[str, dict],
) -> None:
    assert summaries["notes_app/broken.py"]["summary"]["keySymbols"] == []


def test_injected_instructions_never_reach_the_trusted_instructions(
    client: TestClient, analysis_id: str, provider: ScriptedProvider, summaries
) -> None:
    contexts = {}

    class Capture(ScriptedProvider):
        def summarize(self, context, repair_feedback=()):
            contexts[context.path] = context
            return super().summarize(context, repair_feedback)

    store = client.app.state.store
    service = CodeSummaryService(
        store,
        AiConfig(enabled=True, api_key="offline", model="capture-model"),
        provider=Capture(ANSWERS["good"]),
        fetcher=GitHubRawSourceFetcher(url_opener=CannedGitHub()),
    )
    service.generate_summary(analysis_id, "notes_app/plugins.py")

    request = build_request(AiConfig(), contexts["notes_app/plugins.py"])
    assert request["instructions"] == SYSTEM_INSTRUCTIONS
    assert "ignore all previous instructions" not in request["instructions"]
    assert "ignore all previous instructions" in request["input"][0]["content"][1]["text"]


@pytest.mark.parametrize(
    "name",
    [name for name, case in ANSWERS["bad"].items() if case["rejectedBy"] == "structural"],
)
def test_structurally_invalid_answers_are_rejected_and_not_cached(name: str) -> None:
    bad = ANSWERS["bad"][name]
    provider = ScriptedProvider(patched_answers(bad))

    def factory(store: SqliteGraphStore) -> CodeSummaryService:
        from benchmarks.ai_summary_eval import FixtureSourceFetcher

        return CodeSummaryService(
            store,
            AiConfig(enabled=True, api_key="offline", max_input_chars=EVAL_MAX_INPUT_CHARS),
            provider=provider,
            fetcher=FixtureSourceFetcher(),
        )

    ai, _ = run_service(factory)

    assert ai[bad["path"]].error is not None
    assert ai[bad["path"]].error.startswith("AI_SUMMARY_UNVERIFIED")
    # One repair attempt was made with the verification problems as feedback.
    attempts = [feedback for path, feedback in provider.calls if path == bad["path"]]
    assert len(attempts) == 2 and attempts[1]


@pytest.mark.parametrize(
    "name",
    [name for name, case in ANSWERS["bad"].items() if case["rejectedBy"] == "semantic"],
)
def test_semantic_failures_pass_structural_checks_but_fail_the_evaluation(name: str) -> None:
    """Structural validation cannot catch everything; this is why the eval exists."""
    bad = ANSWERS["bad"][name]

    def factory(store: SqliteGraphStore) -> CodeSummaryService:
        from benchmarks.ai_summary_eval import FixtureSourceFetcher

        return CodeSummaryService(
            store,
            AiConfig(enabled=True, api_key="offline", max_input_chars=EVAL_MAX_INPUT_CHARS),
            provider=ScriptedProvider(patched_answers(bad)),
            fetcher=FixtureSourceFetcher(),
        )

    ai, _ = run_service(factory)

    result = ai[bad["path"]]
    assert result.error is None, "expected the structural checks to accept it"
    assert not result.passed
    assert result.forbidden_hits or result.contradiction_flagged is False


def test_the_deterministic_baseline_misses_what_the_code_does() -> None:
    def factory(store: SqliteGraphStore) -> CodeSummaryService:
        from benchmarks.ai_summary_eval import FixtureSourceFetcher

        return CodeSummaryService(
            store,
            AiConfig(enabled=True, api_key="offline", max_input_chars=EVAL_MAX_INPUT_CHARS),
            provider=ScriptedProvider(ANSWERS["good"]),
            fetcher=FixtureSourceFetcher(),
        )

    _, baseline = run_service(factory)

    # No docstrings: the baseline can only count symbols.
    assert baseline["notes_app/auth.py"].behaviors_hit == 0
    # Misleading docstring: the baseline repeats it.
    assert baseline["notes_app/cache.py"].forbidden_hits


def test_the_overview_labels_ai_descriptions_without_reordering(
    client: TestClient, analysis_id: str, summaries: dict[str, dict]
) -> None:
    overview = client.get(f"/analyses/{analysis_id}/overview").json()

    tour = {item["path"]: item for item in overview["tour"]}
    for path, item in tour.items():
        if path in summaries:
            assert item["summarySource"] == "ai"
            assert item["summary"] == summaries[path]["summary"]["summary"]
        else:
            assert item["summarySource"] == "static"

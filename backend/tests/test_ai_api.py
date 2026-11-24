"""AI summary service through the HTTP API, with a fake provider and fetcher.

No test here sends a request to OpenAI or GitHub.
"""

import asyncio
import hashlib
import logging
import threading
import time

import httpx
from fastapi.testclient import TestClient
import pytest

from repolens.ai import AiConfig, CodeSummaryService
from repolens.ai.errors import ProviderTimeoutError, ProviderUnavailableError
from repolens.api.app import create_app
from repolens.api.server import create_server_from_environment
from repolens.graph import SqliteGraphStore

from tests.ai_fixture import (
    ANALYSIS_ID,
    AUTH_SOURCE,
    REPO_URL,
    SHA,
    FakeFetcher,
    FakeProvider,
    good_auth_answer,
    make_service,
    seed_store,
)


SUMMARY_URL = f"/analyses/{ANALYSIS_ID}/ai-summaries/app/auth.py"


def _client(service: CodeSummaryService, store: SqliteGraphStore) -> TestClient:
    return TestClient(create_app(store, summaries=service))


@pytest.fixture
def store() -> SqliteGraphStore:
    return seed_store()


def test_with_ai_disabled_every_existing_feature_still_works(store: SqliteGraphStore) -> None:
    client = TestClient(create_app(store))

    assert client.get("/ai/status").json()["enabled"] is False
    for method in ("get", "post"):
        response = getattr(client, method)(SUMMARY_URL)
        assert response.status_code == 503
        assert response.json()["code"] == "AI_DISABLED"
        assert set(response.json()) == {"code", "message", "hint"}
    assert client.get(f"/analyses/{ANALYSIS_ID}/files/app/auth.py").status_code == 200
    assert client.get(f"/analyses/{ANALYSIS_ID}/graph").status_code == 200
    assert client.get(f"/analyses/{ANALYSIS_ID}/search", params={"q": "sign"}).status_code == 200
    overview = client.get(f"/analyses/{ANALYSIS_ID}/overview").json()
    assert overview["tour"]


def test_enabled_without_a_key_counts_as_disabled(store: SqliteGraphStore) -> None:
    service = CodeSummaryService(store, AiConfig(enabled=True), fetcher=FakeFetcher())

    response = _client(service, store).post(SUMMARY_URL)

    assert response.json()["code"] == "AI_DISABLED"


def test_get_reports_not_generated_without_calling_anything(store: SqliteGraphStore) -> None:
    provider, fetcher = FakeProvider(good_auth_answer()), FakeFetcher()
    client = _client(make_service(store, provider, fetcher), store)

    response = client.get(SUMMARY_URL)

    assert response.status_code == 200
    assert response.json() == {
        "analysisId": ANALYSIS_ID,
        "path": "app/auth.py",
        "sha": SHA,
        "status": "notGenerated",
        "summary": None,
        "metadata": None,
    }
    assert response.headers["cache-control"] == "no-store"
    assert provider.calls == [] and fetcher.requests == []


def test_generating_fetches_the_analyzed_commit_and_returns_a_verified_summary(
    store: SqliteGraphStore,
) -> None:
    provider, fetcher = FakeProvider(good_auth_answer()), FakeFetcher()
    client = _client(make_service(store, provider, fetcher), store)

    response = client.post(SUMMARY_URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert fetcher.requests == [(REPO_URL, SHA, "app/auth.py")]
    assert provider.calls[0][0].commit_sha == SHA
    assert body["status"] == "completed"
    assert body["sha"] == SHA
    assert body["summary"]["keySymbols"][0] == {
        "name": "sign",
        "kind": "function",
        "description": "Issues a signed token.",
        "line": 7,
        "url": f"{REPO_URL}/blob/{SHA}/app/auth.py#L7",
    }
    assert body["summary"]["evidence"][0]["url"] == f"{REPO_URL}/blob/{SHA}/app/auth.py#L7-L11"
    metadata = body["metadata"]
    assert metadata["model"] == "gpt-5.4-mini"
    assert metadata["cached"] is False and metadata["cacheStatus"] == "miss"
    assert metadata["sourceHash"] == hashlib.sha256(AUTH_SOURCE.encode()).hexdigest()
    assert metadata["coverage"] == "complete"
    assert metadata["inspectedLines"] == [[1, 29]]
    assert metadata["promptVersion"] and metadata["schemaVersion"] == "1"
    assert metadata["sourceUrl"] == f"{REPO_URL}/blob/{SHA}/app/auth.py"


def test_repeat_requests_are_served_from_the_cache(store: SqliteGraphStore) -> None:
    provider, fetcher = FakeProvider(good_auth_answer()), FakeFetcher()
    client = _client(make_service(store, provider, fetcher), store)

    first = client.post(SUMMARY_URL).json()
    second = client.post(SUMMARY_URL).json()
    read = client.get(SUMMARY_URL).json()

    assert len(provider.calls) == 1 and len(fetcher.requests) == 1
    assert second["summary"] == first["summary"] == read["summary"]
    assert second["metadata"]["cached"] is True
    assert second["metadata"]["cacheStatus"] == "hit"
    usage = client.get("/ai/status").json()["usage"]
    assert (usage["cacheHits"], usage["cacheMisses"], usage["modelCalls"]) == (1, 1, 1)


def test_a_cache_survives_a_new_service_on_the_same_database(tmp_path) -> None:
    path = str(tmp_path / "repolens.db")
    store = seed_store(store=SqliteGraphStore(path))
    make_service(store).generate_summary(ANALYSIS_ID, "app/auth.py")
    store.close()

    reopened = SqliteGraphStore(path)
    provider = FakeProvider(good_auth_answer())
    payload = make_service(reopened, provider).generate_summary(ANALYSIS_ID, "app/auth.py")

    assert payload["metadata"]["cached"] is True and provider.calls == []


def test_changing_the_model_prompt_or_schema_invalidates_the_cache(
    store: SqliteGraphStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_service(store).generate_summary(ANALYSIS_ID, "app/auth.py")

    other_model = FakeProvider(good_auth_answer())
    make_service(store, other_model, model="another-model").generate_summary(
        ANALYSIS_ID, "app/auth.py"
    )
    assert len(other_model.calls) == 1

    monkeypatch.setattr("repolens.ai.service.PROMPT_VERSION", "test-prompt-v2")
    new_prompt = FakeProvider(good_auth_answer())
    make_service(store, new_prompt).generate_summary(ANALYSIS_ID, "app/auth.py")
    assert len(new_prompt.calls) == 1

    monkeypatch.setattr("repolens.ai.service.SCHEMA_VERSION", "test-schema-v2")
    new_schema = FakeProvider(good_auth_answer())
    make_service(store, new_schema).generate_summary(ANALYSIS_ID, "app/auth.py")
    assert len(new_schema.calls) == 1


def test_summaries_expire_and_are_evicted_with_their_analysis() -> None:
    store = seed_store(expires_in=0.5)
    make_service(store).generate_summary(ANALYSIS_ID, "app/auth.py")
    assert store._conn.execute("SELECT COUNT(*) FROM ai_summaries").fetchone()[0] == 1
    row = store._conn.execute("SELECT expires_at FROM ai_summaries").fetchone()
    analysis = store._conn.execute("SELECT expires_at FROM analyses").fetchone()
    assert row[0] == analysis[0]

    time.sleep(0.6)
    response = _client(make_service(store), store).post(SUMMARY_URL)
    assert response.status_code == 410
    assert response.json()["code"] == "ANALYSIS_EXPIRED"

    store.evict_expired()
    assert store._conn.execute("SELECT COUNT(*) FROM ai_summaries").fetchone()[0] == 0


def test_regeneration_is_rate_limited_then_replaces_the_cached_summary(
    store: SqliteGraphStore,
) -> None:
    now = [1_000_000.0]
    provider = FakeProvider(
        good_auth_answer(), good_auth_answer(summary="Signs and verifies session tokens.")
    )
    client = _client(make_service(store, provider, clock=lambda: now[0]), store)
    client.post(SUMMARY_URL)

    too_soon = client.post(SUMMARY_URL, params={"regenerate": "true"})
    assert too_soon.status_code == 429
    assert too_soon.json()["code"] == "AI_REGENERATE_COOLDOWN"
    assert "60 seconds" in too_soon.json()["hint"]

    now[0] += 61
    regenerated = client.post(SUMMARY_URL, params={"regenerate": "true"}).json()

    assert len(provider.calls) == 2
    assert regenerated["metadata"]["cacheStatus"] == "regenerated"
    assert regenerated["summary"]["summary"] == "Signs and verifies session tokens."
    assert client.get(SUMMARY_URL).json()["summary"]["summary"] == regenerated["summary"]["summary"]
    assert store._conn.execute("SELECT COUNT(*) FROM ai_summaries").fetchone()[0] == 1


def test_an_invalid_answer_gets_one_repair_attempt(store: SqliteGraphStore) -> None:
    bad = good_auth_answer(
        keySymbols=[{"name": "refresh", "kind": "function", "description": "x", "line": 3}]
    )
    provider = FakeProvider(bad, good_auth_answer())
    client = _client(make_service(store, provider), store)

    response = client.post(SUMMARY_URL)

    assert response.status_code == 200
    assert len(provider.calls) == 2
    assert provider.calls[0][1] == ()
    assert provider.calls[1][1] == (
        "keySymbols 'refresh' is not defined in this file's syntax tree.",
    )
    usage = client.get("/ai/status").json()["usage"]
    assert (usage["modelCalls"], usage["validationFailures"]) == (2, 1)


def test_an_answer_that_stays_invalid_is_never_cached_or_shown(store: SqliteGraphStore) -> None:
    bad = good_auth_answer(
        dependencies=[{"path": "app/db.py", "relationship": "imports", "description": "x"}]
    )
    provider = FakeProvider(bad)
    client = _client(make_service(store, provider), store)

    response = client.post(SUMMARY_URL)

    assert response.status_code == 502
    assert response.json()["code"] == "AI_SUMMARY_UNVERIFIED"
    assert "app/db.py" not in response.text
    assert len(provider.calls) == 2
    assert client.get(SUMMARY_URL).json()["status"] == "notGenerated"
    assert store._conn.execute("SELECT COUNT(*) FROM ai_summaries").fetchone()[0] == 0
    assert client.get(f"/analyses/{ANALYSIS_ID}").json()["status"] == "completed"


@pytest.mark.parametrize(
    "error, status, code",
    [
        (ProviderTimeoutError(), 504, "AI_TIMEOUT"),
        (ProviderUnavailableError(), 502, "AI_UNAVAILABLE"),
        (RuntimeError("sdk bug"), 502, "AI_UNAVAILABLE"),
    ],
)
def test_provider_failures_are_summary_errors_and_leave_the_analysis_intact(
    store: SqliteGraphStore, error: Exception, status: int, code: str
) -> None:
    client = _client(make_service(store, FakeProvider(error)), store)

    response = client.post(SUMMARY_URL)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert client.get(f"/analyses/{ANALYSIS_ID}").json()["status"] == "completed"
    assert client.get(f"/analyses/{ANALYSIS_ID}/files/app/auth.py").status_code == 200
    assert client.get(f"/analyses/{ANALYSIS_ID}/search", params={"q": "check"}).status_code == 200
    assert client.get(f"/analyses/{ANALYSIS_ID}/overview").status_code == 200
    assert client.get("/ai/status").json()["usage"]["providerFailures"] == 1


def test_the_daily_call_limit_is_enforced(store: SqliteGraphStore) -> None:
    provider = FakeProvider(
        lambda context: good_auth_answer()
        if context.path == "app/auth.py"
        else {
            "summary": "Holds the signing secret.",
            "purpose": "Configuration.",
            "responsibilities": ["Defines `SECRET`."],
            "keySymbols": [],
            "dependencies": [],
            "sideEffects": [],
            "uncertainties": [],
            "evidence": [{"startLine": 1, "endLine": 1, "description": "x"}],
            "coverage": "complete",
        }
    )
    client = _client(make_service(store, provider, daily_call_limit=1), store)

    assert client.post(SUMMARY_URL).status_code == 200
    blocked = client.post(f"/analyses/{ANALYSIS_ID}/ai-summaries/app/config.py")

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "AI_DAILY_LIMIT"
    assert len(provider.calls) == 1
    # Cached summaries are still served once the budget is spent.
    assert client.post(SUMMARY_URL).status_code == 200


def test_a_repair_attempt_counts_against_the_daily_limit(store: SqliteGraphStore) -> None:
    bad = good_auth_answer(evidence=[{"startLine": 90, "endLine": 99, "description": "x"}])
    provider = FakeProvider(bad, good_auth_answer())
    client = _client(make_service(store, provider, daily_call_limit=1), store)

    response = client.post(SUMMARY_URL)

    assert response.json()["code"] == "AI_DAILY_LIMIT"
    assert len(provider.calls) == 1


def test_concurrent_requests_for_one_file_share_one_model_call(store: SqliteGraphStore) -> None:
    gate = threading.Event()
    provider = FakeProvider(good_auth_answer(), gate=gate)
    service = make_service(store, provider)
    results: list[dict] = []

    def request() -> None:
        results.append(service.generate_summary(ANALYSIS_ID, "app/auth.py"))

    threads = [threading.Thread(target=request) for _ in range(4)]
    for thread in threads:
        thread.start()
    assert provider.started.wait(timeout=5)
    time.sleep(0.1)  # Let the other requests reach the in-flight wait.
    gate.set()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 4
    assert len(provider.calls) == 1
    assert len({result["metadata"]["sourceHash"] for result in results}) == 1


def test_the_global_concurrency_limit_answers_busy(store: SqliteGraphStore) -> None:
    gate = threading.Event()
    provider = FakeProvider(
        lambda context: good_auth_answer()
        if context.path == "app/auth.py"
        else good_auth_answer(),
        gate=gate,
    )
    service = make_service(store, provider, max_concurrent_requests=1)
    holder = threading.Thread(
        target=lambda: service.generate_summary(ANALYSIS_ID, "app/auth.py")
    )
    holder.start()
    assert provider.started.wait(timeout=5)

    response = _client(service, store).post(f"/analyses/{ANALYSIS_ID}/ai-summaries/main.py")

    gate.set()
    holder.join(timeout=10)
    assert response.status_code == 429
    assert response.json()["code"] == "AI_BUSY"


def test_source_that_does_not_match_the_analyzed_commit_is_refused(
    store: SqliteGraphStore,
) -> None:
    changed = AUTH_SOURCE.replace("def check(token):", "def verify(token):")
    provider = FakeProvider(good_auth_answer())
    fetcher = FakeFetcher({"app/auth.py": changed})

    response = _client(make_service(store, provider, fetcher), store).post(SUMMARY_URL)

    assert response.status_code == 409
    assert response.json()["code"] == "SOURCE_MISMATCH"
    assert provider.calls == []


@pytest.mark.parametrize(
    "path, status, code",
    [
        ("/analyses/analysis-missing0001/ai-summaries/app/auth.py", 404, "ANALYSIS_NOT_FOUND"),
        ("/analyses/bad%20id/ai-summaries/app/auth.py", 404, "ANALYSIS_NOT_FOUND"),
        (f"/analyses/{ANALYSIS_ID}/ai-summaries/app/missing.py", 404, "FILE_NOT_FOUND"),
        # The client normalizes `..` away, so no API route matches at all.
        (f"/analyses/{ANALYSIS_ID}/ai-summaries/app/../../etc/passwd", 404, None),
        (f"/analyses/{ANALYSIS_ID}/ai-summaries/%2e%2e/secrets.py", 404, "FILE_NOT_FOUND"),
    ],
)
def test_unknown_analyses_files_and_traversal_are_not_found(
    store: SqliteGraphStore, path: str, status: int, code: str | None
) -> None:
    fetcher = FakeFetcher()
    client = _client(make_service(store, fetcher=fetcher), store)

    response = client.post(path)

    assert response.status_code == status, response.text
    assert response.json().get("code") == code
    assert fetcher.requests == []


def test_unfinished_analyses_cannot_be_summarized() -> None:
    store = SqliteGraphStore()
    row, _ = store.start_or_reuse_analysis(REPO_URL, None, SHA)

    response = _client(make_service(store), store).post(
        f"/analyses/{row['id']}/ai-summaries/app/auth.py"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_NOT_READY"


def test_generating_a_file_summary_does_not_create_a_duplicate_overview_surface(
    store: SqliteGraphStore,
) -> None:
    client = _client(make_service(store), store)
    first = client.get(f"/analyses/{ANALYSIS_ID}/overview")

    client.post(SUMMARY_URL)
    second = client.get(
        f"/analyses/{ANALYSIS_ID}/overview", headers={"If-None-Match": first.headers["etag"]}
    )

    assert first.headers["cache-control"] == "private, immutable"
    assert second.status_code == 304


def test_status_reports_usage_and_estimated_cost_without_secrets(
    store: SqliteGraphStore,
) -> None:
    service = make_service(
        store, input_cost_per_million=0.5, output_cost_per_million=2.0, api_key="sk-secret"
    )
    client = _client(service, store)
    client.post(SUMMARY_URL)

    status = client.get("/ai/status")

    assert "sk-secret" not in status.text
    body = status.json()
    assert body["enabled"] is True and body["model"] == "gpt-5.4-mini"
    assert "source code" in body["notice"]
    assert body["usage"]["inputTokens"] == 1200 and body["usage"]["outputTokens"] == 300
    assert body["usage"]["estimatedCostUsd"] == pytest.approx(
        (1200 * 0.5 + 300 * 2.0) / 1_000_000
    )


def test_usage_logs_never_contain_source_or_the_key(
    store: SqliteGraphStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    make_service(store, api_key="sk-log-secret").generate_summary(ANALYSIS_ID, "app/auth.py")

    assert "AI summary call" in caplog.text
    assert "input_tokens=1200" in caplog.text
    assert "sk-log-secret" not in caplog.text
    assert "hmac.new(SECRET" not in caplog.text


def test_generation_does_not_block_the_event_loop(store: SqliteGraphStore) -> None:
    gate = threading.Event()
    provider = FakeProvider(good_auth_answer(), gate=gate)
    app = create_app(store, summaries=make_service(store, provider))

    async def scenario() -> tuple[int, int]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            generating = asyncio.create_task(client.post(SUMMARY_URL))
            while not provider.started.is_set():
                await asyncio.sleep(0.01)
            health = await asyncio.wait_for(client.get("/health"), timeout=2)
            assert not generating.done()
            gate.set()
            return health.status_code, (await generating).status_code

    assert asyncio.run(scenario()) == (200, 200)


def test_the_server_reads_ai_settings_from_the_environment() -> None:
    off = TestClient(create_server_from_environment({}, runner=None))
    assert off.get("/api/ai/status").json()["enabled"] is False

    on = TestClient(
        create_server_from_environment(
            {
                "REPOLENS_AI_ENABLED": "true",
                "OPENAI_API_KEY": "sk-env-secret",
                "REPOLENS_AI_MODEL": "configured-model",
            }
        )
    )
    status = on.get("/api/ai/status")
    assert status.json()["enabled"] is True
    assert status.json()["model"] == "configured-model"
    assert "sk-env-secret" not in status.text

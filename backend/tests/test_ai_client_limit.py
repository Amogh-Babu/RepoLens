"""The per-visitor hourly limit on new AI summaries.

No test here sends a request to OpenAI or GitHub.
"""

from typing import Any

from fastapi.testclient import TestClient
import pytest

from repolens.ai.errors import ClientLimitError, ProviderUnavailableError, SourceFetchError
from repolens.ai.limits import ClientLimitReached, ClientRateLimiter
from repolens.api.app import create_app
from repolens.graph import SqliteGraphStore

from tests.ai_fixture import (
    ANALYSIS_ID,
    FakeFetcher,
    FakeProvider,
    good_auth_answer,
    make_service,
    seed_store,
)


def _url(path: str) -> str:
    return f"/analyses/{ANALYSIS_ID}/ai-summaries/{path}"


def _answer(context: Any) -> dict[str, Any]:
    """A verifiable answer for any fixture file."""
    if context.path == "app/auth.py":
        return good_auth_answer()
    return {
        "summary": "A small module.",
        "purpose": "Supports the app.",
        "responsibilities": ["Holds a few definitions."],
        "keySymbols": [],
        "dependencies": [],
        "sideEffects": [],
        "uncertainties": [],
        "evidence": [{"startLine": 1, "endLine": 1, "description": "The first line."}],
        "coverage": "complete",
    }


@pytest.fixture
def store() -> SqliteGraphStore:
    return seed_store()


# --- ClientRateLimiter -------------------------------------------------------


def test_the_limiter_allows_the_limit_then_reports_the_wait() -> None:
    now = [1_000.0]
    limiter = ClientRateLimiter(2, lambda: now[0])
    limiter.acquire("a")
    now[0] += 600
    limiter.acquire("a")

    with pytest.raises(ClientLimitReached) as caught:
        limiter.acquire("a")

    assert caught.value.limit == 2
    assert caught.value.retry_after_seconds == 3000


def test_the_limiter_window_slides() -> None:
    now = [1_000.0]
    limiter = ClientRateLimiter(1, lambda: now[0])
    limiter.acquire("a")
    now[0] += 3600

    assert limiter.acquire("a") is not None


def test_the_limiter_keeps_visitors_apart_and_can_give_back() -> None:
    limiter = ClientRateLimiter(1, lambda: 0.0)
    ticket = limiter.acquire("a")
    limiter.acquire("b")
    limiter.release("a", ticket)

    assert limiter.acquire("a") is not None
    with pytest.raises(ClientLimitReached):
        limiter.acquire("b")


def test_a_zero_limit_never_limits() -> None:
    limiter = ClientRateLimiter(0, lambda: 0.0)

    assert all(limiter.acquire("a") is None for _ in range(50))


# --- Through the HTTP API ----------------------------------------------------


def test_a_visitor_over_the_limit_gets_a_clear_429_and_keeps_cached_summaries(
    store: SqliteGraphStore,
) -> None:
    provider = FakeProvider(_answer)
    client = TestClient(
        create_app(store, summaries=make_service(store, provider, client_hourly_limit=2))
    )

    assert client.post(_url("app/auth.py")).status_code == 200
    assert client.post(_url("app/config.py")).status_code == 200
    blocked = client.post(_url("main.py"))

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "AI_CLIENT_LIMIT"
    assert body["message"] == "You have generated 2 new AI summaries in the last hour."
    assert "about 60 minutes" in body["hint"]
    assert blocked.headers["retry-after"] == "3600"
    assert blocked.headers["cache-control"] == "no-store"
    assert len(provider.calls) == 2
    # Cached summaries are free and still served.
    assert client.post(_url("app/auth.py")).status_code == 200
    assert client.get(_url("main.py")).json()["status"] == "notGenerated"


# --- In the service ----------------------------------------------------------


def test_each_visitor_has_its_own_budget_and_cache_hits_are_free(
    store: SqliteGraphStore,
) -> None:
    provider = FakeProvider(_answer)
    service = make_service(store, provider, client_hourly_limit=1)

    service.generate_summary(ANALYSIS_ID, "app/auth.py", client="10.0.0.1")
    service.generate_summary(ANALYSIS_ID, "app/config.py", client="10.0.0.2")
    # Another visitor's cached summary costs nothing.
    cached = service.generate_summary(ANALYSIS_ID, "app/config.py", client="10.0.0.1")

    assert cached["metadata"]["cacheStatus"] == "hit"
    with pytest.raises(ClientLimitError):
        service.generate_summary(ANALYSIS_ID, "main.py", client="10.0.0.1")
    assert len(provider.calls) == 2


def test_the_budget_refills_after_an_hour(store: SqliteGraphStore) -> None:
    now = [1_000_000.0]
    service = make_service(
        store, FakeProvider(_answer), clock=lambda: now[0], client_hourly_limit=1
    )
    service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")
    with pytest.raises(ClientLimitError):
        service.generate_summary(ANALYSIS_ID, "app/config.py", client="v")

    now[0] += 3600

    service.generate_summary(ANALYSIS_ID, "app/config.py", client="v")


def test_a_regeneration_counts_as_a_new_summary(store: SqliteGraphStore) -> None:
    now = [1_000_000.0]
    service = make_service(
        store, FakeProvider(_answer), clock=lambda: now[0], client_hourly_limit=1
    )
    service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")
    now[0] += 61

    with pytest.raises(ClientLimitError):
        service.generate_summary(ANALYSIS_ID, "app/auth.py", regenerate=True, client="v")


class _FailingOnceFetcher(FakeFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def fetch(self, repo_url: str, sha: str, path: str) -> str:
        if not self.failed:
            self.failed = True
            raise SourceFetchError("GitHub is down.")
        return super().fetch(repo_url, sha, path)


def test_a_failure_before_any_model_call_is_not_counted(store: SqliteGraphStore) -> None:
    provider = FakeProvider(_answer)
    service = make_service(
        store, provider, fetcher=_FailingOnceFetcher(), client_hourly_limit=1
    )

    with pytest.raises(SourceFetchError):
        service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")
    result = service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")

    assert result["status"] == "completed"
    assert len(provider.calls) == 1


def test_a_failed_model_call_still_counts(store: SqliteGraphStore) -> None:
    provider = FakeProvider(ProviderUnavailableError(), _answer)
    service = make_service(store, provider, client_hourly_limit=1)

    with pytest.raises(ProviderUnavailableError):
        service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")
    with pytest.raises(ClientLimitError):
        service.generate_summary(ANALYSIS_ID, "app/auth.py", client="v")


def test_without_a_client_or_with_a_zero_limit_nothing_is_limited(
    store: SqliteGraphStore,
) -> None:
    unnamed = make_service(store, FakeProvider(_answer), client_hourly_limit=1)
    for path in ("app/auth.py", "app/config.py", "main.py"):
        unnamed.generate_summary(ANALYSIS_ID, path)

    off = make_service(seed_store(), FakeProvider(_answer), client_hourly_limit=0)
    for path in ("app/auth.py", "app/config.py", "main.py"):
        off.generate_summary(ANALYSIS_ID, path, client="v")

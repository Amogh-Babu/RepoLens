"""Shared helpers for the AI summary tests: a seeded store, fakes, answers.

Nothing here makes a network request. Sources are parsed by the existing
analyzer exactly as the pipeline would, so stored symbols always match.
"""

from collections.abc import Callable, Mapping
import threading
from typing import Any

from repolens.ai import AiConfig, CodeSummaryService
from repolens.ai.models import CodeSummaryContext, ProviderResult, ProviderUsage
from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files
from repolens.analysis.models import RepositoryAnalysis
from repolens.graph import AnalysisRecord, SqliteGraphStore


REPO_URL = "https://github.com/repolens-fixtures/tokens"
SHA = "c0ffee" + "0" * 34
ANALYSIS_ID = "analysis-ai0000000001"

AUTH_SOURCE = '''\
import hmac
import time

from app.config import SECRET


def sign(user_id, ttl=60):
    expires = int(time.time()) + ttl
    payload = f"{user_id}:{expires}"
    mac = hmac.new(SECRET, payload.encode(), "sha256").hexdigest()
    return f"{payload}:{mac}"


def check(token):
    user_id, expires, mac = token.rsplit(":", 2)
    good = hmac.new(SECRET, f"{user_id}:{expires}".encode(), "sha256").hexdigest()
    if not hmac.compare_digest(good, mac) or int(expires) < time.time():
        return None
    return user_id


class Sessions:
    def __init__(self):
        self.active = {}

    def open(self, user_id):
        token = sign(user_id)
        self.active[token] = user_id
        return token
'''

CONFIG_SOURCE = 'SECRET = b"dev"\n'
MAIN_SOURCE = "from app.auth import Sessions\n\nSESSIONS = Sessions()\n"

DEFAULT_SOURCES = {
    "app/__init__.py": "",
    "app/auth.py": AUTH_SOURCE,
    "app/config.py": CONFIG_SOURCE,
    "main.py": MAIN_SOURCE,
}


def seed_store(
    sources: Mapping[str, str] = DEFAULT_SOURCES,
    *,
    store: SqliteGraphStore | None = None,
    analysis_id: str = ANALYSIS_ID,
    repo_url: str = REPO_URL,
    sha: str = SHA,
    expires_in: float = 3600.0,
) -> SqliteGraphStore:
    """Analyze in-memory `sources` like the pipeline does and store the result."""
    import time

    service = AnalysisService()
    parsed = tuple(
        service.analyze_source(path, text) for path, text in sorted(sources.items())
    )
    analysis = RepositoryAnalysis(root="/fixture", files=parsed)
    target = store if store is not None else SqliteGraphStore()
    now = time.time()
    target.save(
        AnalysisRecord(
            analysis_id=analysis_id,
            repo=repo_url,
            sha=sha,
            status="completed",
            created_at=now,
            expires_at=now + expires_in,
            files=classify_imports(to_analyzed_files(analysis)),
            embeddings=(),
        )
    )
    return target


class FakeFetcher:
    """A `SourceFetcher` serving in-memory sources and recording requests."""

    def __init__(self, sources: Mapping[str, str] = DEFAULT_SOURCES) -> None:
        self.sources = dict(sources)
        self.requests: list[tuple[str, str, str]] = []

    def fetch(self, repo_url: str, sha: str, path: str) -> str:
        self.requests.append((repo_url, sha, path))
        return self.sources[path]


Answer = Mapping[str, Any] | Exception | Callable[[CodeSummaryContext], Any]


class FakeProvider:
    """A `CodeSummaryProvider` that replays scripted answers.

    Each call takes the next answer (the last one repeats): a payload dict,
    an exception to raise, or a callable receiving the context. With
    `gate`, every call waits for the event first, to hold calls in flight.
    """

    def __init__(
        self,
        *answers: Answer,
        usage: ProviderUsage = ProviderUsage(input_tokens=1200, output_tokens=300),
        gate: threading.Event | None = None,
    ) -> None:
        self._answers = list(answers)
        self._usage = usage
        self._gate = gate
        self._lock = threading.Lock()
        self.calls: list[tuple[CodeSummaryContext, tuple[str, ...]]] = []
        self.started = threading.Event()

    def summarize(
        self, context: CodeSummaryContext, repair_feedback: tuple[str, ...] = ()
    ) -> ProviderResult:
        with self._lock:
            self.calls.append((context, repair_feedback))
            index = min(len(self.calls), len(self._answers)) - 1
        self.started.set()
        if self._gate is not None:
            assert self._gate.wait(timeout=10), "test gate never opened"
        answer = self._answers[index]
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            answer = answer(context)
        return ProviderResult(payload=dict(answer), model="fake-model", usage=self._usage)


def good_auth_answer(**overrides: Any) -> dict[str, Any]:
    """A correct summary of `AUTH_SOURCE`, as a well-behaved model would answer."""
    answer: dict[str, Any] = {
        "summary": "Signs and checks expiring HMAC tokens and keeps an in-memory registry of open sessions.",
        "purpose": "Token-based authentication for the app.",
        "responsibilities": [
            "Signs `user_id:expires` payloads with HMAC-SHA256 using `SECRET`.",
            "Rejects tokens whose signature does not match or that have expired.",
            "Opens sessions by issuing a token and recording it in `Sessions.active`.",
        ],
        "keySymbols": [
            {"name": "sign", "kind": "function", "description": "Issues a signed token.", "line": 7},
            {"name": "check", "kind": "function", "description": "Validates a token.", "line": 14},
            {"name": "Sessions", "kind": "class", "description": "Session registry.", "line": 22},
            {"name": "Sessions.open", "kind": "method", "description": "Starts a session.", "line": 26},
        ],
        "dependencies": [
            {"path": "app/config.py", "relationship": "imports", "description": "The signing secret."},
            {"path": "main.py", "relationship": "importedBy", "description": "Creates the session registry."},
        ],
        "sideEffects": [],
        "uncertainties": [],
        "evidence": [
            {"startLine": 7, "endLine": 11, "description": "Token signing."},
            {"startLine": 14, "endLine": 19, "description": "Signature and expiry check."},
        ],
        "coverage": "complete",
    }
    answer.update(overrides)
    return answer


def make_service(
    store: SqliteGraphStore,
    provider: FakeProvider | None = None,
    fetcher: FakeFetcher | None = None,
    clock: Callable[[], float] | None = None,
    **config: Any,
) -> CodeSummaryService:
    """Build an enabled service around fakes; `config` overrides `AiConfig`."""
    settings: dict[str, Any] = {"enabled": True, "api_key": "test-key", **config}
    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    return CodeSummaryService(
        store,
        AiConfig(**settings),
        provider=provider if provider is not None else FakeProvider(good_auth_answer()),
        fetcher=fetcher if fetcher is not None else FakeFetcher(),
        slot_wait_seconds=0.2,
        **kwargs,
    )

"""Generate, verify, cache, and serve AI overviews of search results.

One request explains the top results of one search, on demand:

    run the search (same query, same reading goal) -> top 8 results
    cached for this query, goal and ranking? -> serve it
    else -> build a bounded context from stored analysis data and any
            verified AI file summaries already cached (nothing downloaded)
         -> call the model (the limits file summaries use apply)
         -> verify every recommended path and code name against the results
            (one repair attempt if verification fails)
         -> cache the verified overview in SQLite and serve it

Like file summaries, `get_overview` only reads the cache and only
`generate_overview` (an explicit click) calls the model. The overview shares
the file summaries' model, configuration, concurrency slots, per-visitor
hourly budget and daily call budget through their `AiGate`.
"""

from collections.abc import Callable
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any

from repolens.ai.errors import (
    AiDisabledError,
    DailyLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RegenerateCooldownError,
    SearchOverviewValidationError,
    SummaryBusyError,
    SummaryError,
)
from repolens.ai.search_context import build_search_context
from repolens.ai.search_models import (
    SEARCH_SCHEMA_VERSION,
    SearchOverview,
    SearchOverviewContext,
)
from repolens.ai.search_prompts import SEARCH_PROMPT_VERSION
from repolens.ai.search_provider import (
    SEARCH_FALLBACK,
    SEARCH_TASK,
    OpenAISearchOverviewProvider,
    SearchOverviewProvider,
)
from repolens.ai.search_validation import validate_search_overview
from repolens.ai.service import MAX_ATTEMPTS, CodeSummaryService
from repolens.graph.store import SqliteGraphStore
from repolens.search import SearchService
from repolens.search.service import SearchIntent


_LOGGER = logging.getLogger(__name__)

SEARCH_NOTICE = (
    "Generating an overview sends the file names, symbol names, docstring lines "
    "and cached AI file summaries of these search results to the configured AI "
    "provider ({provider}). No source code is sent."
)


def _today(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class SearchOverviewService:
    """On-demand, cache-first AI overviews of a search's top results."""

    def __init__(
        self,
        store: SqliteGraphStore,
        summaries: CodeSummaryService,
        *,
        search_service: SearchService | None = None,
        provider: SearchOverviewProvider | None = None,
    ) -> None:
        """Initialize the service.

        Args:
          store: The graph store, which also holds the overview cache.
          summaries: The file summary service: its configuration, its limits
            (`summaries.gate`) and its cached summaries are shared.
          search_service: The search the reading list uses; built on `store`
            when omitted.
          provider: Model provider; defaults to OpenAI when AI is active.
            Tests inject a fake so no request leaves the process.
        """
        self._store = store
        self._summaries = summaries
        self._config = summaries.config
        self._gate = summaries.gate
        self._clock: Callable[[], float] = self._gate.clock
        self._search = search_service if search_service is not None else SearchService(store)
        self._provider = provider
        if self._provider is None and summaries.active:
            self._provider = OpenAISearchOverviewProvider(self._config)
        self._inflight: dict[tuple[str, ...], Future[dict[str, Any]]] = {}
        self._inflight_lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._summaries.active and self._provider is not None

    def notice(self) -> str | None:
        """Return the provider notice shown before generating an overview."""
        return SEARCH_NOTICE.format(provider="OpenAI") if self.active else None

    def get_overview(
        self, analysis_id: str, query: str, intent: SearchIntent | None
    ) -> dict[str, Any]:
        """Return the cached overview of a search, without generating one.

        Raises:
          AiDisabledError: AI is off.
          QueryValidationError: The query is empty or too long.
          GraphStoreError / AnalysisUnavailableError: Unknown, expired, or
            unfinished analysis.
        """
        context = self._context(analysis_id, query, intent)
        if not context.files:
            return self._empty(analysis_id, context, "noResults")
        row = self._cached_row(analysis_id, context)
        if row is None:
            return self._empty(analysis_id, context, "notGenerated")
        return self._payload(analysis_id, context, row, cached=True, cache_status="hit")

    def generate_overview(
        self,
        analysis_id: str,
        query: str,
        intent: SearchIntent | None,
        *,
        regenerate: bool = False,
        client: str | None = None,
    ) -> dict[str, Any]:
        """Return a verified overview, generating it if it is not cached.

        Same rules as `CodeSummaryService.generate_summary`: a cache hit is
        free; a new generation counts against the visitor's hourly budget and
        the daily call budget (shared with file summaries); `regenerate`
        replaces a cached overview at most once per cooldown; concurrent
        requests for the same search share one generation.

        Raises:
          SummaryError: AI is off, a limit is reached, the provider failed,
            or the answer failed verification.
          QueryValidationError, GraphStoreError, AnalysisUnavailableError.
        """
        context = self._context(analysis_id, query, intent)
        if not context.files:
            return self._empty(analysis_id, context, "noResults")
        day = _today(self._clock())
        row = self._cached_row(analysis_id, context)
        if row is not None and not regenerate:
            self._store.record_ai_usage(day, cache_hits=1)
            return self._payload(analysis_id, context, row, cached=True, cache_status="hit")
        if row is not None:
            elapsed = self._clock() - float(row["created_at"])
            cooldown = self._config.regenerate_cooldown_seconds
            if elapsed < cooldown:
                raise RegenerateCooldownError(max(1, int(cooldown - elapsed + 0.999)))

        key = (analysis_id, context.query_norm, context.intent or "", context.results_hash)
        ticket: float | None = None
        with self._inflight_lock:
            pending = self._inflight.get(key)
            if pending is None:
                ticket = self._gate.acquire_client(client)
                future: Future[dict[str, Any]] = Future()
                self._inflight[key] = future
        if pending is not None:
            return self._wait_for(pending)

        called_model = False

        def note_model_call() -> None:
            nonlocal called_model
            called_model = True

        try:
            payload = self._generate(
                analysis_id,
                context,
                cache_status="regenerated" if row is not None else "miss",
                on_model_call=note_model_call,
            )
        except BaseException as error:
            if not called_model:
                # Nothing was spent, so the visitor keeps this generation.
                self._gate.release_client(client, ticket)
            future.set_exception(error)
            raise
        else:
            future.set_result(payload)
            return payload
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)

    def _context(
        self, analysis_id: str, query: str, intent: SearchIntent | None
    ) -> SearchOverviewContext:
        if not self.active:
            raise AiDisabledError()
        return build_search_context(
            self._search,
            self._store.get_search_documents(analysis_id),
            self._summaries.cached_summary_texts(analysis_id),
            analysis_id,
            query,
            intent,
            max_input_chars=self._config.max_input_chars,
        )

    def _wait_for(self, pending: "Future[dict[str, Any]]") -> dict[str, Any]:
        limit = (
            (self._config.timeout_seconds + 5.0) * MAX_ATTEMPTS
            + self._gate.slot_wait_seconds
        )
        try:
            return pending.result(timeout=limit)
        except FutureTimeoutError:
            raise SummaryBusyError() from None

    def _cached_row(self, analysis_id: str, context: SearchOverviewContext) -> Any:
        return self._store.get_ai_search_overview(
            analysis_id,
            query_norm=context.query_norm,
            intent=context.intent or "",
            results_hash=context.results_hash,
            model_id=self._config.model,
            prompt_version=SEARCH_PROMPT_VERSION,
            schema_version=SEARCH_SCHEMA_VERSION,
        )

    def _generate(
        self,
        analysis_id: str,
        context: SearchOverviewContext,
        *,
        cache_status: str,
        on_model_call: Callable[[], None],
    ) -> dict[str, Any]:
        day = _today(self._clock())
        self._store.record_ai_usage(day, cache_misses=1)
        if self._store.get_ai_usage(day)["calls"] >= self._config.daily_call_limit:
            raise DailyLimitError()
        with self._gate.slot():
            overview = self._call_and_verify(analysis_id, context, day, on_model_call)
        row = self._store.save_ai_search_overview(
            analysis_id,
            query_norm=context.query_norm,
            intent=context.intent or "",
            results_hash=context.results_hash,
            model_id=self._config.model,
            prompt_version=SEARCH_PROMPT_VERSION,
            schema_version=SEARCH_SCHEMA_VERSION,
            used_file_summaries=json.dumps(list(context.used_file_summaries)),
            overview_json=overview.model_dump_json(by_alias=True),
            created_at=self._clock(),
        )
        return self._payload(analysis_id, context, row, cached=False, cache_status=cache_status)

    def _call_and_verify(
        self,
        analysis_id: str,
        context: SearchOverviewContext,
        day: str,
        on_model_call: Callable[[], None],
    ) -> SearchOverview:
        """Call the model, verify, and repair once; return a verified overview."""
        assert self._provider is not None
        feedback: tuple[str, ...] = ()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not self._gate.reserve_call(day):
                raise DailyLimitError()
            on_model_call()
            started = time.monotonic()
            try:
                result = self._provider.overview(context, feedback)
            except (ProviderTimeoutError, ProviderUnavailableError):
                self._store.record_ai_usage(day, provider_failures=1)
                _LOGGER.warning(
                    "AI search overview provider call failed: analysis=%s attempt=%d",
                    analysis_id,
                    attempt,
                )
                raise
            except SummaryError:
                raise
            except Exception:
                self._store.record_ai_usage(day, provider_failures=1)
                _LOGGER.exception(
                    "AI search overview provider raised unexpectedly: analysis=%s",
                    analysis_id,
                )
                raise ProviderUnavailableError(
                    f"The AI provider could not {SEARCH_TASK}.", SEARCH_FALLBACK
                ) from None
            latency_ms = int((time.monotonic() - started) * 1000)
            usage = result.usage
            self._store.record_ai_usage(
                day,
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                latency_ms=latency_ms,
            )
            verdict = validate_search_overview(result.payload, context)
            # The query is the user's text: it is never logged.
            _LOGGER.info(
                "AI search overview call: feature=search analysis=%s model=%s "
                "attempt=%d results=%d input_tokens=%s output_tokens=%s "
                "latency_ms=%d verified=%s problems=%d",
                analysis_id,
                result.model,
                attempt,
                len(context.files),
                usage.input_tokens,
                usage.output_tokens,
                latency_ms,
                verdict.ok,
                len(verdict.problems),
            )
            if verdict.ok and verdict.overview is not None:
                return verdict.overview
            self._store.record_ai_usage(day, validation_failures=1)
            feedback = verdict.problems
        raise SearchOverviewValidationError(feedback)

    def _empty(
        self, analysis_id: str, context: SearchOverviewContext, status: str
    ) -> dict[str, Any]:
        return {
            "analysisId": analysis_id,
            "query": context.query,
            "intent": context.intent,
            "status": status,
            "overview": None,
            "metadata": None,
        }

    def _payload(
        self,
        analysis_id: str,
        context: SearchOverviewContext,
        row: Any,
        *,
        cached: bool,
        cache_status: str,
    ) -> dict[str, Any]:
        return {
            "analysisId": analysis_id,
            "query": context.query,
            "intent": context.intent,
            "status": "completed",
            "overview": json.loads(str(row["overview_json"])),
            "metadata": {
                "model": str(row["model_id"]),
                "promptVersion": str(row["prompt_version"]),
                "schemaVersion": str(row["schema_version"]),
                "generatedAt": _iso(float(row["created_at"])),
                "cached": cached,
                "cacheStatus": cache_status,
                "usedFileSummaries": json.loads(str(row["used_file_summaries"])),
            },
        }

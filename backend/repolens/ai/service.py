"""Generate, verify, cache, and serve AI summaries of analyzed files.

One request summarizes one file, on demand:

    cached? -> serve it
    else    -> download the file at the analyzed commit
            -> re-parse it with the existing analyzer and check it matches
            -> build a bounded, line-numbered context
            -> call the model (concurrency and daily limits apply)
            -> verify the answer against the source and the graph
               (one repair attempt if verification fails)
            -> cache the verified summary in SQLite and serve it

Requests for the same file that arrive while it is being generated wait for
that one generation instead of starting their own model call. Nothing here
changes the analysis: any failure is a summary-specific error, and the graph,
search, overview, and deterministic descriptions keep working.

This module is synchronous and thread-safe. FastAPI runs its routes on a
worker thread, so a slow model call never blocks the event loop.
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

from repolens.ai.config import AiConfig
from repolens.ai.context import build_context
from repolens.ai.errors import (
    AiDisabledError,
    ClientLimitError,
    DailyLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RegenerateCooldownError,
    SourceRejectedError,
    SummaryBusyError,
    SummaryError,
    SummaryValidationError,
)
from repolens.ai.limits import ClientLimitReached, ClientRateLimiter
from repolens.ai.models import SCHEMA_VERSION, CodeSummary, CodeSummaryContext
from repolens.ai.prompts import PROMPT_VERSION
from repolens.ai.provider import CodeSummaryProvider, OpenAICodeSummaryProvider
from repolens.ai.source import GitHubRawSourceFetcher, SourceFetcher, validate_repo_path
from repolens.ai.validation import validate_summary
from repolens.analysis import AnalysisService
from repolens.graph.models import FileDetail
from repolens.graph.store import SqliteGraphStore, build_github_source_url


_LOGGER = logging.getLogger(__name__)

# One answer plus at most one repair attempt per generation.
MAX_ATTEMPTS = 2

PROVIDER_NOTICE = (
    "Generating a summary sends this file's source code and its static-analysis "
    "metadata to the configured AI provider ({provider}). Search and the "
    "dependency map stay local."
)


def _today(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class CodeSummaryService:
    """On-demand, cache-first AI summaries for files of a completed analysis."""

    def __init__(
        self,
        store: SqliteGraphStore,
        config: AiConfig,
        *,
        provider: CodeSummaryProvider | None = None,
        fetcher: SourceFetcher | None = None,
        analysis_service: AnalysisService | None = None,
        clock: Callable[[], float] = time.time,
        slot_wait_seconds: float = 5.0,
    ) -> None:
        """Initialize the service.

        Args:
          store: The graph store, which also holds the summary cache.
          config: Switches and limits; summaries need `config.active`.
          provider: Model provider; defaults to OpenAI when active. Tests
            inject a fake so no request leaves the process.
          fetcher: Source downloader; defaults to GitHub raw content.
          analysis_service: Parser used to re-check downloaded source.
          clock: Time source, replaceable in tests.
          slot_wait_seconds: How long a request waits for a free model slot
            before answering AI_BUSY.
        """
        self._store = store
        self._config = config
        self._provider = provider
        if self._provider is None and config.active:
            self._provider = OpenAICodeSummaryProvider(config)
        self._fetcher = fetcher if fetcher is not None else GitHubRawSourceFetcher()
        self._analysis_service = (
            analysis_service if analysis_service is not None else AnalysisService()
        )
        self._clock = clock
        self._slot_wait_seconds = slot_wait_seconds
        self._slots = threading.BoundedSemaphore(config.max_concurrent_requests)
        self._client_limiter = ClientRateLimiter(config.client_hourly_limit, clock)
        self._inflight: dict[tuple[str, str], Future[dict[str, Any]]] = {}
        self._inflight_lock = threading.Lock()

    @property
    def config(self) -> AiConfig:
        return self._config

    @property
    def active(self) -> bool:
        """Whether summaries can be generated and served."""
        return self._config.active and self._provider is not None

    def status(self) -> dict[str, Any]:
        """Return whether AI is on, the notice to show, and today's usage."""
        if not self.active:
            return {
                "enabled": False,
                "provider": None,
                "model": None,
                "notice": None,
                "dailyCallLimit": None,
                "usage": None,
            }
        day = _today(self._clock())
        usage = self._store.get_ai_usage(day)
        lookups = usage["cache_hits"] + usage["cache_misses"]
        return {
            "enabled": True,
            "provider": "OpenAI",
            "model": self._config.model,
            "notice": PROVIDER_NOTICE.format(provider="OpenAI"),
            "dailyCallLimit": self._config.daily_call_limit,
            "usage": {
                "day": day,
                "modelCalls": usage["calls"],
                "inputTokens": usage["input_tokens"],
                "outputTokens": usage["output_tokens"],
                "cacheHits": usage["cache_hits"],
                "cacheMisses": usage["cache_misses"],
                "cacheHitRate": (
                    round(usage["cache_hits"] / lookups, 4) if lookups else None
                ),
                "validationFailures": usage["validation_failures"],
                "providerFailures": usage["provider_failures"],
                "averageLatencyMs": (
                    round(usage["latency_ms"] / usage["calls"]) if usage["calls"] else None
                ),
                "estimatedCostUsd": self._estimate_cost(
                    usage["input_tokens"], usage["output_tokens"]
                ),
            },
        }

    def cached_summary_texts(self, analysis_id: str) -> dict[str, str]:
        """Return `{path: summary}` for verified summaries of one analysis.

        The overview uses this to prefer a verified AI description over the
        deterministic one; it never generates anything.
        """
        if not self.active:
            return {}
        return self._store.get_ai_summary_texts(
            analysis_id,
            model_id=self._config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )

    def get_summary(self, analysis_id: str, path: str) -> dict[str, Any]:
        """Return the cached summary of a file, without generating one.

        Raises:
          AiDisabledError: AI summaries are off.
          GraphStoreError: Unknown, expired, or unfinished analysis, or a file
            that is not part of it.
          SourceRejectedError: The file is not a supported source file.
        """
        detail = self._eligible_file(analysis_id, path)
        row = self._cached_row(analysis_id, detail.path)
        if row is None:
            return {
                "analysisId": analysis_id,
                "path": detail.path,
                "sha": detail.sha,
                "status": "notGenerated",
                "summary": None,
                "metadata": None,
            }
        return self._payload(detail, row, cached=True, cache_status="hit")

    def generate_summary(
        self,
        analysis_id: str,
        path: str,
        *,
        regenerate: bool = False,
        client: str | None = None,
    ) -> dict[str, Any]:
        """Return a verified summary, generating it if it is not cached.

        With `regenerate`, a cached summary is replaced, at most once per
        cooldown period. Concurrent requests for the same file share one
        generation.

        `client` identifies the visitor (the API passes the client IP
        address). A new generation counts against that visitor's hourly
        limit; cache hits and joining a generation in flight do not. Without
        a `client`, no per-visitor limit applies.

        Raises:
          SummaryError: AI is off, the source cannot be fetched or does not
            match, a limit is reached, the provider failed, or the answer
            failed verification. The analysis itself is never changed.
          GraphStoreError: Unknown, expired, or unfinished analysis or file.
        """
        detail = self._eligible_file(analysis_id, path)
        day = _today(self._clock())
        row = self._cached_row(analysis_id, detail.path)
        if row is not None and not regenerate:
            self._store.record_ai_usage(day, cache_hits=1)
            return self._payload(detail, row, cached=True, cache_status="hit")
        if row is not None:
            elapsed = self._clock() - float(row["created_at"])
            cooldown = self._config.regenerate_cooldown_seconds
            if elapsed < cooldown:
                raise RegenerateCooldownError(max(1, int(cooldown - elapsed + 0.999)))

        key = (analysis_id, detail.path)
        ticket: float | None = None
        with self._inflight_lock:
            pending = self._inflight.get(key)
            if pending is None:
                if client is not None:
                    try:
                        ticket = self._client_limiter.acquire(client)
                    except ClientLimitReached as limited:
                        raise ClientLimitError(
                            limited.limit, limited.retry_after_seconds
                        ) from None
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
                detail,
                cache_status="regenerated" if row is not None else "miss",
                on_model_call=note_model_call,
            )
        except BaseException as error:
            if client is not None and not called_model:
                # Nothing was spent, so the visitor keeps this generation.
                self._client_limiter.release(client, ticket)
            future.set_exception(error)
            raise
        else:
            future.set_result(payload)
            return payload
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)

    def _wait_for(self, pending: "Future[dict[str, Any]]") -> dict[str, Any]:
        """Wait for another request's generation of the same file."""
        limit = (self._config.timeout_seconds + 5.0) * MAX_ATTEMPTS + self._slot_wait_seconds
        try:
            return pending.result(timeout=limit)
        except FutureTimeoutError:
            raise SummaryBusyError() from None

    def _eligible_file(self, analysis_id: str, path: str) -> FileDetail:
        if not self.active:
            raise AiDisabledError()
        detail = self._store.get_file(analysis_id, path)
        validate_repo_path(detail.path)
        return detail

    def _cached_row(self, analysis_id: str, path: str) -> Any:
        return self._store.get_ai_summary(
            analysis_id,
            path,
            model_id=self._config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )

    def _generate(
        self,
        analysis_id: str,
        detail: FileDetail,
        *,
        cache_status: str,
        on_model_call: Callable[[], None] = lambda: None,
    ) -> dict[str, Any]:
        day = _today(self._clock())
        self._store.record_ai_usage(day, cache_misses=1)
        if self._store.get_ai_usage(day)["calls"] >= self._config.daily_call_limit:
            raise DailyLimitError()

        source = self._fetcher.fetch(detail.repo, detail.sha, detail.path)
        try:
            parsed = self._analysis_service.analyze_source(detail.path, source)
        except ValueError:
            raise SourceRejectedError("Only Python source files can be summarized.") from None
        context = build_context(
            detail=detail,
            parsed=parsed,
            source=source,
            max_input_chars=self._config.max_input_chars,
        )

        if not self._slots.acquire(timeout=self._slot_wait_seconds):
            raise SummaryBusyError()
        try:
            summary = self._call_and_verify(analysis_id, context, day, on_model_call)
        finally:
            self._slots.release()

        row = self._store.save_ai_summary(
            analysis_id,
            detail.path,
            source_hash=context.source_hash,
            model_id=self._config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            coverage=context.coverage,
            inspected_lines=json.dumps([list(span) for span in context.inspected_lines]),
            line_count=context.line_count,
            summary_json=summary.model_dump_json(by_alias=True),
            created_at=self._clock(),
        )
        return self._payload(detail, row, cached=False, cache_status=cache_status)

    def _call_and_verify(
        self,
        analysis_id: str,
        context: CodeSummaryContext,
        day: str,
        on_model_call: Callable[[], None] = lambda: None,
    ) -> CodeSummary:
        """Call the model, verify, and repair once; return a verified summary.

        `on_model_call` runs once a model call is reserved, just before it is
        made, so callers can tell spent generations from abandoned ones.
        """
        assert self._provider is not None
        feedback: tuple[str, ...] = ()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not self._store.reserve_ai_call(day, self._config.daily_call_limit):
                raise DailyLimitError()
            on_model_call()
            started = time.monotonic()
            try:
                result = self._provider.summarize(context, feedback)
            except (ProviderTimeoutError, ProviderUnavailableError):
                self._store.record_ai_usage(day, provider_failures=1)
                _LOGGER.warning(
                    "AI summary provider call failed: analysis=%s path=%s attempt=%d",
                    analysis_id,
                    context.path,
                    attempt,
                )
                raise
            except SummaryError:
                raise
            except Exception:
                self._store.record_ai_usage(day, provider_failures=1)
                _LOGGER.exception(
                    "AI summary provider raised unexpectedly: analysis=%s path=%s",
                    analysis_id,
                    context.path,
                )
                raise ProviderUnavailableError() from None
            latency_ms = int((time.monotonic() - started) * 1000)
            usage = result.usage
            self._store.record_ai_usage(
                day,
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                latency_ms=latency_ms,
            )
            verdict = validate_summary(result.payload, context)
            _LOGGER.info(
                "AI summary call: analysis=%s path=%s model=%s attempt=%d "
                "input_tokens=%s output_tokens=%s latency_ms=%d "
                "estimated_cost_usd=%s coverage=%s verified=%s problems=%d",
                analysis_id,
                context.path,
                result.model,
                attempt,
                usage.input_tokens,
                usage.output_tokens,
                latency_ms,
                self._estimate_cost(usage.input_tokens or 0, usage.output_tokens or 0),
                context.coverage,
                verdict.ok,
                len(verdict.problems),
            )
            if verdict.ok and verdict.summary is not None:
                return verdict.summary
            self._store.record_ai_usage(day, validation_failures=1)
            feedback = verdict.problems
        raise SummaryValidationError(feedback)

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Estimate USD cost from configured prices; None when none are set."""
        input_price = self._config.input_cost_per_million
        output_price = self._config.output_cost_per_million
        if input_price is None or output_price is None:
            return None
        return round(
            (input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6
        )

    def _payload(
        self,
        detail: FileDetail,
        row: Any,
        *,
        cached: bool,
        cache_status: str,
    ) -> dict[str, Any]:
        """Serialize a cached row with links pinned to the analyzed commit."""
        summary = json.loads(str(row["summary_json"]))
        blob = build_github_source_url(detail.repo, detail.sha, detail.path)

        def link(start: int, end: int) -> str:
            return f"{blob}#L{start}" if start == end else f"{blob}#L{start}-L{end}"

        for item in summary.get("keySymbols", []):
            item["url"] = link(item["line"], item["line"])
        for item in summary.get("evidence", []):
            item["url"] = link(item["startLine"], item["endLine"])
        for item in summary.get("sideEffects", []):
            item["url"] = link(item["startLine"], item["endLine"])
        return {
            "analysisId": detail.analysis_id,
            "path": detail.path,
            "sha": detail.sha,
            "status": "completed",
            "summary": summary,
            "metadata": {
                "model": str(row["model_id"]),
                "promptVersion": str(row["prompt_version"]),
                "schemaVersion": str(row["schema_version"]),
                "sourceHash": str(row["source_hash"]),
                "generatedAt": _iso(float(row["created_at"])),
                "cached": cached,
                "cacheStatus": cache_status,
                "coverage": str(row["coverage"]),
                "inspectedLines": json.loads(str(row["inspected_lines"])),
                "lineCount": int(row["line_count"]),
                "sourceUrl": blob,
            },
        }

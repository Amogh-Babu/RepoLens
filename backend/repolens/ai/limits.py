"""Per-visitor limit on new AI summaries.

The daily call limit caps what the whole server spends, but on a public
deployment one visitor could use all of it. `ClientRateLimiter` gives each
visitor (identified by client IP address) a sliding one-hour budget of new
summary generations, so everyone else keeps theirs.

Only generations count: cached summaries, and requests that join a
generation already in flight, are free. A generation that ends before any
model call (unsupported file, GitHub download failure, busy, daily limit) is
handed back with `release`, so visitors pay only for real model work.

State lives in process memory, so it resets when the server restarts. That
is enough for one server process, which is how RepoLens runs.
"""

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import math
import threading
from typing import Any


WINDOW_SECONDS = 3600.0

# Past this many tracked visitors, idle entries are swept on the next acquire
# so the table cannot grow without bound.
_SWEEP_THRESHOLD = 10_000


class ClientRateLimiter:
    """Allow each client at most `limit` acquisitions per sliding hour."""

    def __init__(self, limit: int, clock: Callable[[], float]) -> None:
        """Initialize the limiter.

        Args:
          limit: Acquisitions allowed per client per hour; 0 means unlimited.
          clock: Time source in seconds, shared with the summary service.
        """
        self._limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        self._history: dict[str, deque[float]] = {}

    @property
    def limit(self) -> int:
        return self._limit

    def acquire(self, client: str) -> float | None:
        """Record one acquisition for `client`.

        Returns:
          A ticket to pass to `release`, or None when the limit is off.

        Raises:
          ClientLimitReached: The client used its whole budget this hour.
        """
        if self._limit <= 0:
            return None
        now = self._clock()
        with self._lock:
            if len(self._history) > _SWEEP_THRESHOLD:
                self._sweep(now)
            history = self._history.setdefault(client, deque())
            _expire(history, now)
            if len(history) >= self._limit:
                wait = history[0] + WINDOW_SECONDS - now
                raise ClientLimitReached(self._limit, max(1, math.ceil(wait)))
            history.append(now)
            return now

    def release(self, client: str, ticket: float | None) -> None:
        """Give back an acquisition that did not lead to a model call."""
        if ticket is None:
            return
        with self._lock:
            history = self._history.get(client)
            if history is None:
                return
            try:
                history.remove(ticket)
            except ValueError:
                return
            if not history:
                del self._history[client]

    def _sweep(self, now: float) -> None:
        for client in list(self._history):
            history = self._history[client]
            _expire(history, now)
            if not history:
                del self._history[client]


def _expire(history: deque[float], now: float) -> None:
    while history and history[0] <= now - WINDOW_SECONDS:
        history.popleft()


class ClientLimitReached(Exception):
    """Raised by `ClientRateLimiter.acquire` when a client is out of budget."""

    def __init__(self, limit: int, retry_after_seconds: int) -> None:
        super().__init__(f"client limit of {limit} per hour reached")
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds


class AiGate:
    """The limits every AI feature shares: one per server, not per feature.

    File summaries and search overviews draw on the same concurrency slots,
    the same per-visitor hourly budget, and the same daily call budget (kept
    in the store's `ai_usage` row), so an operator sets and watches one set
    of limits in `/ai/status`.
    """

    def __init__(
        self,
        store: Any,
        config: Any,
        *,
        clock: Callable[[], float],
        slot_wait_seconds: float = 5.0,
    ) -> None:
        """Initialize the gate.

        Args:
          store: The graph store (`reserve_ai_call` / `record_ai_usage`).
          config: The `AiConfig` whose limits apply.
          clock: Time source, shared with the services.
          slot_wait_seconds: How long a request waits for a free model slot
            before answering AI_BUSY.
        """
        self._store = store
        self._config = config
        self.clock = clock
        self.slot_wait_seconds = slot_wait_seconds
        self._slots = threading.BoundedSemaphore(config.max_concurrent_requests)
        self._client_limiter = ClientRateLimiter(config.client_hourly_limit, clock)

    def acquire_client(self, client: str | None) -> float | None:
        """Count one new generation against `client`'s hourly budget.

        Returns a ticket for `release_client`, or None without a client or
        limit.

        Raises:
          ClientLimitError: The visitor used its hourly budget.
        """
        if client is None:
            return None
        from repolens.ai.errors import ClientLimitError

        try:
            return self._client_limiter.acquire(client)
        except ClientLimitReached as limited:
            raise ClientLimitError(limited.limit, limited.retry_after_seconds) from None

    def release_client(self, client: str | None, ticket: float | None) -> None:
        """Give back a generation that ended before any model call."""
        if client is not None:
            self._client_limiter.release(client, ticket)

    def reserve_call(self, day: str) -> bool:
        """Count one model call against today's budget, if any is left."""
        return self._store.reserve_ai_call(day, self._config.daily_call_limit)

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one model-call slot.

        Raises:
          SummaryBusyError: No slot became free in time.
        """
        from repolens.ai.errors import SummaryBusyError

        if not self._slots.acquire(timeout=self.slot_wait_seconds):
            raise SummaryBusyError()
        try:
            yield
        finally:
            self._slots.release()

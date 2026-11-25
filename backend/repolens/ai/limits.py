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
from collections.abc import Callable
import math
import threading


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

"""A repository module that shadows the standard library `queue`.

The repository root is on `sys.path` while the application runs, so
`import queue` in `main.py` reaches this file and not the standard library.
"""

from collections import deque


class JobQueue:
    """A FIFO of pending job names."""

    def __init__(self) -> None:
        self._items: deque[str] = deque()

    def push(self, name: str) -> None:
        """Add one job to the back of the queue."""
        self._items.append(name)

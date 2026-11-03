"""The engine, re-exported by library.core."""

from __future__ import annotations

import threading

from library.core.registry import Registry


class Engine:
    """Runs every registered job once."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._lock = threading.Lock()

    def run(self) -> None:
        """Run the registered jobs under the engine lock."""
        with self._lock:
            self._registry.run_all()


def run_engine(registry: Registry) -> Engine:
    """Build an engine for `registry` and run it."""
    engine = Engine(registry)
    engine.run()
    return engine

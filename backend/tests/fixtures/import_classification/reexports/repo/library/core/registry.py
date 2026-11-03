"""The registry, re-exported by library.core."""

import collections.abc

JOBS: dict[str, collections.abc.Callable[[], None]] = {}


class Registry:
    """Holds the jobs the engine runs."""

    def register(self, name: str, job: collections.abc.Callable[[], None]) -> None:
        """Record one job under `name`."""
        JOBS[name] = job

    def run_all(self) -> None:
        """Run every registered job."""
        for job in JOBS.values():
            job()

"""Protocol definitions for RepoLens repository ingestion.

The seams here keep the network transport and the Git host behind interfaces:
tests substitute an in-memory fetcher, and a second host (such as GitLab) can
implement ``RepoSource`` without touching the rest of the pipeline.
"""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from repolens.ingestion.models import Snapshot


class UrlOpener(Protocol):
    """Open an https URL for reading, as ``urllib.request.urlopen`` does."""

    def __call__(self, url: str, timeout: float) -> AbstractContextManager[Any]:
        """Return a context-managed response object exposing ``read(size)``."""
        ...


class ArchiveFetcher(Protocol):
    """Download one repository archive to a local file."""

    def fetch(self, url: str, destination: Path) -> int:
        """Write the archive at url to destination and return bytes written."""
        ...


class RepoSource(Protocol):
    """Produce an on-disk snapshot of a repository pinned to one commit."""

    def fetch_snapshot(self, repo_url: str, sha: str, destination: Path) -> Snapshot:
        """Download and extract the repository at sha into destination."""
        ...

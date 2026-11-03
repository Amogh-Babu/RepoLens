"""Data models for RepoLens repository ingestion.

These models hold plain data only. Nothing in this package imports, executes,
or evaluates any content from a downloaded repository.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepoCoordinate:
    """A validated repository location on a supported Git host."""

    host: str
    owner: str
    name: str

    @property
    def repo_url(self) -> str:
        """Return the normalized https URL for the repository root."""
        return f"https://{self.host}/{self.owner}/{self.name}"

    @property
    def slug(self) -> str:
        """Return the '<owner>/<name>' short form used in messages."""
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class ArchiveLimits:
    """Timeout and size caps applied to ingestion of one repository.

    The caps bound work done on untrusted input: a compressed archive that is
    too large is never downloaded in full, and a small archive that expands to
    an unreasonable size on disk is abandoned mid-extraction.

    The last three caps bound the reviewable source a snapshot yields after
    vendored and generated files are filtered out
    (``repolens.ingestion.filters``): a single file past ``max_file_bytes`` is
    excluded from analysis, and a repository whose remaining files exceed
    ``max_analyzable_bytes`` or ``max_analyzable_file_count`` is rejected
    instead of analyzed.
    """

    max_archive_bytes: int = 256 * 1024 * 1024
    max_extracted_bytes: int = 1024 * 1024 * 1024
    max_file_count: int = 50_000
    timeout_seconds: float = 30.0
    max_file_bytes: int = 2 * 1024 * 1024
    max_analyzable_bytes: int = 128 * 1024 * 1024
    max_analyzable_file_count: int = 20_000


@dataclass(frozen=True)
class Snapshot:
    """An extracted repository snapshot pinned to one commit SHA."""

    repo: str
    sha: str
    root: str
    files: tuple[str, ...] = ()

    @property
    def file_count(self) -> int:
        return len(self.files)

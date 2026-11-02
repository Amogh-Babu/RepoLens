"""RepoLens repository ingestion package.

Downloads one archive for a (repository URL, commit SHA) pair and extracts it
to disk. Repository content is never imported, executed, or evaluated.
"""

from repolens.ingestion.archive import extract_zip_archive
from repolens.ingestion.errors import (
    ArchiveDownloadError,
    ArchiveFormatError,
    ArchiveTooLargeError,
    DestinationNotEmptyError,
    GitHubUnavailableError,
    IngestionError,
    InvalidCommitShaError,
    InvalidRepoUrlError,
    NoPythonFilesError,
    RateLimitedError,
    RefNotFoundError,
    RepoEmptyError,
    RepoNotFoundError,
    UnsafeArchiveError,
    UnsupportedHostError,
)
from repolens.ingestion.fetcher import HttpsArchiveFetcher
from repolens.ingestion.models import ArchiveLimits, RepoCoordinate, Snapshot
from repolens.ingestion.ports import ArchiveFetcher, RepoSource, UrlOpener
from repolens.ingestion.resolver import GitHubRefResolver
from repolens.ingestion.source import GitHubSource
from repolens.ingestion.urls import (
    ALLOWED_ARCHIVE_HOSTS,
    ALLOWED_REPO_HOSTS,
    ARCHIVE_HOST,
    build_archive_url,
    is_allowed_archive_url,
    normalize_commit_sha,
    parse_repo_url,
)

__all__ = [
    "ALLOWED_ARCHIVE_HOSTS",
    "ALLOWED_REPO_HOSTS",
    "ARCHIVE_HOST",
    "ArchiveDownloadError",
    "ArchiveFetcher",
    "ArchiveFormatError",
    "ArchiveLimits",
    "ArchiveTooLargeError",
    "DestinationNotEmptyError",
    "GitHubRefResolver",
    "GitHubSource",
    "GitHubUnavailableError",
    "HttpsArchiveFetcher",
    "IngestionError",
    "InvalidCommitShaError",
    "InvalidRepoUrlError",
    "NoPythonFilesError",
    "RateLimitedError",
    "RefNotFoundError",
    "RepoCoordinate",
    "RepoEmptyError",
    "RepoNotFoundError",
    "RepoSource",
    "Snapshot",
    "UnsafeArchiveError",
    "UnsupportedHostError",
    "UrlOpener",
    "build_archive_url",
    "extract_zip_archive",
    "is_allowed_archive_url",
    "normalize_commit_sha",
    "parse_repo_url",
]

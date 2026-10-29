"""RepoLens repository ingestion package.

Downloads one archive for a (repository URL, commit SHA) pair, extracts it to
disk, and decides which extracted files are reviewable source. Repository
content is never imported, executed, or evaluated.
"""

from repolens.ingestion.archive import extract_zip_archive
from repolens.ingestion.errors import (
    ArchiveDownloadError,
    ArchiveFormatError,
    ArchiveTooLargeError,
    DestinationNotEmptyError,
    FileTooLargeError,
    IngestionError,
    InvalidCommitShaError,
    InvalidRepoUrlError,
    RepositoryTooLargeError,
    UnsafeArchiveError,
    UnsupportedHostError,
)
from repolens.ingestion.fetcher import HttpsArchiveFetcher
from repolens.ingestion.filters import (
    GENERATED_DIRECTORY_NAMES,
    GENERATED_DIRECTORY_SUFFIXES,
    GENERATED_FILE_NAMES,
    GENERATED_FILE_SUFFIXES,
    METADATA_DIRECTORY_NAMES,
    VENDORED_DIRECTORY_NAMES,
    ExclusionReason,
    FileExclusion,
    FilterReport,
    SourceFileFilter,
)
from repolens.ingestion.models import ArchiveLimits, RepoCoordinate, Snapshot
from repolens.ingestion.ports import (
    ArchiveFetcher,
    FileFilter,
    RepoSource,
    UrlOpener,
)
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
    "ExclusionReason",
    "FileExclusion",
    "FileFilter",
    "FileTooLargeError",
    "FilterReport",
    "GENERATED_DIRECTORY_NAMES",
    "GENERATED_DIRECTORY_SUFFIXES",
    "GENERATED_FILE_NAMES",
    "GENERATED_FILE_SUFFIXES",
    "GitHubSource",
    "HttpsArchiveFetcher",
    "IngestionError",
    "InvalidCommitShaError",
    "InvalidRepoUrlError",
    "METADATA_DIRECTORY_NAMES",
    "RepoCoordinate",
    "RepoSource",
    "RepositoryTooLargeError",
    "Snapshot",
    "SourceFileFilter",
    "UnsafeArchiveError",
    "UnsupportedHostError",
    "UrlOpener",
    "VENDORED_DIRECTORY_NAMES",
    "build_archive_url",
    "extract_zip_archive",
    "is_allowed_archive_url",
    "normalize_commit_sha",
    "parse_repo_url",
]

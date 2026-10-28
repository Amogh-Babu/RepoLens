"""GitHub implementation of the RepoSource port.

``GitHubSource`` downloads one archive for a (repository URL, commit SHA) pair
and extracts it to a snapshot directory. The URL and SHA are validated before
any network call, the archive is deleted once extracted, and a failed snapshot
is discarded rather than left half-written. Repository content is only written
and read as bytes; it is never imported, executed, or evaluated.
"""

from pathlib import Path
import shutil
import tempfile

from repolens.ingestion.archive import extract_zip_archive
from repolens.ingestion.errors import DestinationNotEmptyError
from repolens.ingestion.fetcher import HttpsArchiveFetcher
from repolens.ingestion.models import ArchiveLimits, Snapshot
from repolens.ingestion.ports import ArchiveFetcher
from repolens.ingestion.urls import (
    build_archive_url,
    normalize_commit_sha,
    parse_repo_url,
)


class GitHubSource:
    """Download and extract public GitHub repository snapshots by commit SHA."""

    def __init__(
        self,
        fetcher: ArchiveFetcher | None = None,
        limits: ArchiveLimits = ArchiveLimits(),
    ) -> None:
        """Initialize the source.

        Args:
          fetcher: Archive transport; defaults to ``HttpsArchiveFetcher``.
          limits: Size and timeout caps for downloads and extraction.
        """
        self._limits = limits
        self._fetcher = (
            fetcher if fetcher is not None else HttpsArchiveFetcher(limits=limits)
        )

    def fetch_snapshot(
        self, repo_url: str, sha: str, destination: Path
    ) -> Snapshot:
        """Download the repository at one commit and extract it to disk.

        Args:
          repo_url: Public GitHub repository URL.
          sha: Full 40-character commit SHA to pin the snapshot to.
          destination: Empty or missing directory to extract into.

        Returns:
          The snapshot describing the extracted files.

        Raises:
          InvalidRepoUrlError: The repository URL is malformed or not https.
          UnsupportedHostError: The URL is not a GitHub repository URL.
          InvalidCommitShaError: The SHA is not a full commit SHA.
          DestinationNotEmptyError: The destination already holds files.
          ArchiveDownloadError: The archive could not be downloaded.
          ArchiveTooLargeError: The archive or its contents exceed the limits.
          ArchiveFormatError: The download is not a readable, non-empty zip.
          UnsafeArchiveError: An archive member would escape the snapshot.
        """
        coordinate = parse_repo_url(repo_url)
        normalized_sha = normalize_commit_sha(sha)
        self._require_empty_destination(destination)

        archive_url = build_archive_url(coordinate, normalized_sha)
        work_dir = Path(tempfile.mkdtemp(prefix="repolens-archive-"))
        destination_existed = destination.exists()
        try:
            archive_path = work_dir / f"{normalized_sha}.zip"
            self._fetcher.fetch(archive_url, archive_path)
            files = extract_zip_archive(archive_path, destination, self._limits)
        except BaseException:
            self._discard_snapshot(destination, destination_existed)
            raise
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        return Snapshot(
            repo=coordinate.repo_url,
            sha=normalized_sha,
            root=str(destination),
            files=files,
        )

    def _require_empty_destination(self, destination: Path) -> None:
        """Refuse to write a snapshot over existing files."""
        if destination.exists() and any(destination.iterdir()):
            raise DestinationNotEmptyError(str(destination))

    def _discard_snapshot(self, destination: Path, destination_existed: bool) -> None:
        """Remove a partial snapshot so no caller sees incomplete files."""
        if not destination.exists():
            return
        if destination_existed:
            for child in destination.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            return
        shutil.rmtree(destination, ignore_errors=True)

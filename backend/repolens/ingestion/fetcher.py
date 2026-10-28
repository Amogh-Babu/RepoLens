"""HTTPS download of repository archives.

The fetcher only ever opens https URLs on the GitHub archive host allowlist,
including after redirects, and stops writing as soon as the download exceeds
the configured size cap. It downloads bytes; it never runs them.
"""

from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from repolens.ingestion.errors import (
    ArchiveDownloadError,
    ArchiveTooLargeError,
    InvalidRepoUrlError,
)
from repolens.ingestion.models import ArchiveLimits
from repolens.ingestion.ports import UrlOpener
from repolens.ingestion.urls import ALLOWED_ARCHIVE_HOSTS, is_allowed_archive_url


_DOWNLOAD_CHUNK_BYTES = 64 * 1024
_USER_AGENT = "RepoLens/0.1 (+https://github.com/Amogh-Babu/RepoLens)"
_ARCHIVE_URL_HINT = (
    "Archive downloads are restricted to https://"
    f"{ALLOWED_ARCHIVE_HOSTS[0]}/<owner>/<repo>/zip/<sha>."
)
_RETRY_HINT = "Wait a moment and run the analysis again."


class AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that refuses to follow redirects off the allowlist."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        """Reject redirect targets that are not allowlisted archive URLs."""
        if not is_allowed_archive_url(newurl):
            raise urllib.error.HTTPError(
                newurl, code, f"Refused redirect to {newurl}", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_url_opener() -> UrlOpener:
    """Build a urllib opener that validates redirects and sends no cookies."""
    opener = urllib.request.build_opener(AllowlistedRedirectHandler())

    def open_url(url: str, timeout: float) -> Any:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": _USER_AGENT, "Accept": "application/zip"},
        )
        return opener.open(request, timeout=timeout)

    return open_url


class HttpsArchiveFetcher:
    """Download repository archives over https with host and size limits."""

    def __init__(
        self,
        limits: ArchiveLimits = ArchiveLimits(),
        url_opener: UrlOpener | None = None,
    ) -> None:
        self._limits = limits
        if url_opener is None:
            url_opener = _default_url_opener()
        self._url_opener = url_opener

    def fetch(self, url: str, destination: Path) -> int:
        """Download an archive to destination.

        Args:
          url: Archive URL; must be https on the archive host allowlist.
          destination: File path to write the archive to.

        Returns:
          The number of bytes written.

        Raises:
          InvalidRepoUrlError: The URL is not an allowlisted https archive URL.
          ArchiveTooLargeError: The download exceeds the archive size cap.
          ArchiveDownloadError: The host returned an error or the transfer
            failed.
        """
        if not is_allowed_archive_url(url):
            raise InvalidRepoUrlError(
                message="Archive downloads are only allowed from GitHub.",
                hint=_ARCHIVE_URL_HINT,
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._open(url) as response:
                self._check_content_length(response)
                return self._stream_to_file(response, destination)
        except BaseException:
            _remove_quietly(destination)
            raise

    def _open(self, url: str) -> Any:
        """Open the archive URL, translating transport failures."""
        try:
            return self._url_opener(url, self._limits.timeout_seconds)
        except urllib.error.HTTPError as error:
            raise _download_error_for_status(error.code) from error
        except TimeoutError as error:
            raise ArchiveDownloadError(
                message="The archive download timed out.", hint=_RETRY_HINT
            ) from error
        except urllib.error.URLError as error:
            raise ArchiveDownloadError(
                message=f"The archive could not be downloaded: {error.reason}.",
                hint=_RETRY_HINT,
            ) from error

    def _check_content_length(self, response: object) -> None:
        """Reject an archive whose declared length is over the cap."""
        headers = getattr(response, "headers", None)
        raw_length = headers.get("Content-Length") if headers is not None else None
        if raw_length is None:
            return
        try:
            declared_bytes = int(raw_length)
        except (TypeError, ValueError):
            return
        if declared_bytes > self._limits.max_archive_bytes:
            raise ArchiveTooLargeError(
                f"The repository archive is {declared_bytes} bytes, "
                f"more than the {self._limits.max_archive_bytes} byte limit."
            )

    def _stream_to_file(self, response: object, destination: Path) -> int:
        """Copy the response body to disk, enforcing the archive size cap."""
        written_bytes = 0
        read = getattr(response, "read")
        try:
            with open(destination, "wb") as sink:
                while chunk := read(_DOWNLOAD_CHUNK_BYTES):
                    written_bytes += len(chunk)
                    if written_bytes > self._limits.max_archive_bytes:
                        raise ArchiveTooLargeError(
                            "The repository archive is larger than the "
                            f"{self._limits.max_archive_bytes} byte limit."
                        )
                    sink.write(chunk)
        except (urllib.error.URLError, OSError) as error:
            raise ArchiveDownloadError(
                message=f"The archive download failed: {error}.", hint=_RETRY_HINT
            ) from error
        return written_bytes


def _remove_quietly(path: Path) -> None:
    """Delete a partial download without masking the original failure."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _download_error_for_status(status: int) -> ArchiveDownloadError:
    """Translate an HTTP status into a user-facing download error."""
    if status == 404:
        return ArchiveDownloadError(
            message="The repository or commit was not found on GitHub.",
            hint="Check that the repository is public and the commit SHA exists.",
            status_code=404,
        )
    if status in (403, 429):
        return ArchiveDownloadError(
            message="GitHub rate-limited the archive download.",
            hint=_RETRY_HINT,
            status_code=429,
        )
    return ArchiveDownloadError(
        message=f"GitHub returned HTTP {status} for the archive download.",
        hint=_RETRY_HINT,
    )

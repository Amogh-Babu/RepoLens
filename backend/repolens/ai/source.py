"""Fetch one analyzed file's source, pinned to the analyzed commit.

Snapshots are deleted once parsing finishes, so a summary request downloads
the one file it needs again, from GitHub's raw-content host, at the exact
commit SHA the analysis recorded (never a branch). The URL is built only from
values RepoLens already validated: the stored repository URL (re-checked with
`parse_repo_url`), the stored SHA (re-checked with `normalize_commit_sha`),
and a repository-relative path that must be a file of the analysis. Redirects
off the raw host are refused, the body is capped, and it must decode as UTF-8
text without NUL bytes. Nothing is executed, and the source is kept only in
memory for the length of the request.
"""

from collections.abc import Callable
import hashlib
from pathlib import PurePosixPath
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request

from repolens.ai.errors import (
    SourceFetchError,
    SourceRejectedError,
)
from repolens.analysis.python_analyzer import PYTHON_FILE_EXTENSIONS
from repolens.ingestion.models import ArchiveLimits
from repolens.ingestion.ports import UrlOpener
from repolens.ingestion.urls import normalize_commit_sha, parse_repo_url


RAW_HOST = "raw.githubusercontent.com"
SUPPORTED_EXTENSIONS = PYTHON_FILE_EXTENSIONS

_USER_AGENT = "RepoLens/0.1 (+https://github.com/Amogh-Babu/RepoLens)"
_DEFAULT_TIMEOUT_SECONDS = 15.0


class SourceFetcher(Protocol):
    """Return the text of one repository file at one commit."""

    def fetch(self, repo_url: str, sha: str, path: str) -> str:
        """Download and decode the file, or raise a `SummaryError`."""
        ...


def validate_repo_path(path: str) -> str:
    """Return a safe repository-relative POSIX path, or raise.

    Rejects absolute paths, `..` and `.` segments, backslashes, control
    characters, empty segments, and unsupported extensions, so a path can only
    name a file inside the repository tree.

    Raises:
      SourceRejectedError: The path is unsafe or not a supported source file.
    """
    if not path or len(path) > 400:
        raise SourceRejectedError("The file path is empty or too long.")
    if any(ord(char) < 32 or char in "\\\x7f" for char in path):
        raise SourceRejectedError("The file path contains characters RepoLens does not accept.")
    if path.startswith("/"):
        raise SourceRejectedError("The file path must be relative to the repository.")
    segments = path.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise SourceRejectedError("The file path must not contain empty, '.' or '..' segments.")
    if not path.lower().endswith(SUPPORTED_EXTENSIONS):
        raise SourceRejectedError("Only Python source files can be summarized.")
    return PurePosixPath(path).as_posix()


def build_raw_url(repo_url: str, sha: str, path: str) -> str:
    """Build the raw-content URL for one file at one commit.

    Raises:
      InvalidRepoUrlError: The stored repository URL is not a GitHub repo.
      InvalidCommitShaError: The SHA is not a full commit SHA.
      SourceRejectedError: The path is unsafe.
    """
    coordinate = parse_repo_url(repo_url)
    normalized_sha = normalize_commit_sha(sha)
    safe_path = validate_repo_path(path)
    quoted = "/".join(urllib.parse.quote(segment, safe="") for segment in safe_path.split("/"))
    return (
        f"https://{RAW_HOST}/{urllib.parse.quote(coordinate.owner, safe='')}/"
        f"{urllib.parse.quote(coordinate.name, safe='')}/{normalized_sha}/{quoted}"
    )


def is_allowed_raw_url(url: str) -> bool:
    """Return whether `url` is a plain https URL on the raw-content host."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() != "https":
        return False
    if parts.username is not None or parts.password is not None:
        return False
    try:
        if parts.port is not None:
            return False
    except ValueError:
        return False
    return (parts.hostname or "").lower() == RAW_HOST


class _RawHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that leave the raw-content host."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        if not is_allowed_raw_url(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "Refused redirect off the raw-content host", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_url_opener() -> UrlOpener:
    """Build an opener with no credentials: the GitHub token is never sent."""
    opener = urllib.request.build_opener(_RawHostRedirectHandler())

    def open_url(url: str, timeout: float) -> Any:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": _USER_AGENT, "Accept": "text/plain"},
        )
        return opener.open(request, timeout=timeout)

    return open_url


class GitHubRawSourceFetcher:
    """Download one file from raw.githubusercontent.com at a pinned commit."""

    def __init__(
        self,
        url_opener: UrlOpener | None = None,
        *,
        max_file_bytes: int = ArchiveLimits().max_file_bytes,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the fetcher.

        Args:
          url_opener: Transport; tests pass a fake. Defaults to urllib.
          max_file_bytes: Largest file accepted; the ingestion cap by default,
            since a larger file was never analyzed.
          timeout_seconds: Network timeout for the download.
        """
        self._url_opener = url_opener if url_opener is not None else _default_url_opener()
        self._max_file_bytes = max_file_bytes
        self._timeout_seconds = timeout_seconds

    def fetch(self, repo_url: str, sha: str, path: str) -> str:
        """Return the decoded text of `path` at commit `sha`.

        Raises:
          SourceRejectedError: Unsafe path, oversized, binary, or not UTF-8.
          SourceFetchError: GitHub failed, rate-limited, or did not answer.
        """
        url = build_raw_url(repo_url, sha, path)
        if not is_allowed_raw_url(url):  # Defensive: build_raw_url only makes these.
            raise SourceRejectedError("RepoLens only downloads source from GitHub.")
        try:
            with self._url_opener(url, self._timeout_seconds) as response:
                body = _read_capped(response, self._max_file_bytes)
        except urllib.error.HTTPError as error:
            raise _fetch_error_for_status(error.code) from error
        except TimeoutError as error:
            raise SourceFetchError(
                "GitHub took too long to return the file.", status_code=504
            ) from error
        except urllib.error.URLError as error:
            raise SourceFetchError("GitHub could not be reached for the file.") from error
        return decode_source(body)


def _read_capped(response: Any, max_bytes: int) -> bytes:
    """Read at most `max_bytes`; raise if the body is longer."""
    read: Callable[[int], bytes] = getattr(response, "read")
    body = read(max_bytes + 1)
    if len(body) > max_bytes:
        raise SourceRejectedError(
            f"The file is larger than the {max_bytes} byte limit for summaries."
        )
    return body


def decode_source(body: bytes) -> str:
    """Decode a downloaded file as UTF-8 text, rejecting binary content.

    Raises:
      SourceRejectedError: The bytes hold NUL characters or are not UTF-8.
    """
    if b"\x00" in body:
        raise SourceRejectedError("The file looks like binary content, not source text.")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise SourceRejectedError("The file is not valid UTF-8 text.") from None
    return text.removeprefix("﻿")


def hash_source(source: str) -> str:
    """Return the SHA-256 hex digest of decoded source text."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _fetch_error_for_status(status: int) -> SourceFetchError:
    if status == 404:
        return SourceFetchError(
            "GitHub no longer has this file at the analyzed commit.",
            code="SOURCE_NOT_FOUND",
            status_code=404,
        )
    if status in (403, 429):
        return SourceFetchError(
            "GitHub rate-limited the source download.",
            code="SOURCE_RATE_LIMITED",
            status_code=429,
        )
    return SourceFetchError(f"GitHub returned HTTP {status} for the file.")

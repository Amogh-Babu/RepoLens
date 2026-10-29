"""Resolve a branch, tag, or the default branch to a full commit SHA.

Snapshots are pinned to a commit SHA, so the pipeline asks the GitHub REST API
which commit a ref points at before anything is downloaded. The resolver only
talks to ``api.github.com``, including after redirects (GitHub redirects
renamed repositories), and reads at most one short response body.
"""

import os
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from repolens.ingestion.errors import (
    GitHubUnavailableError,
    InvalidCommitShaError,
    RateLimitedError,
    RefNotFoundError,
    RepoEmptyError,
    RepoNotFoundError,
)
from repolens.ingestion.models import RepoCoordinate
from repolens.ingestion.ports import UrlOpener
from repolens.ingestion.urls import normalize_commit_sha, parse_repo_url


API_HOST = "api.github.com"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

_USER_AGENT = "RepoLens/0.1 (+https://github.com/Amogh-Babu/RepoLens)"
_MAX_RESPONSE_BYTES = 1024
_DEFAULT_TIMEOUT_SECONDS = 10.0


class ApiHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that only follows redirects within the GitHub API."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        """Reject redirect targets outside https://api.github.com."""
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != "https" or parts.netloc.lower() != API_HOST:
            raise urllib.error.HTTPError(
                newurl, code, f"Refused redirect to {newurl}", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_url_opener(token: str | None) -> UrlOpener:
    """Build an opener that asks the commits API for a bare SHA.

    The token, when set, raises GitHub's anonymous rate limit of 60 requests
    an hour. It is only ever sent to ``api.github.com``.
    """
    opener = urllib.request.build_opener(ApiHostRedirectHandler())
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github.sha",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def open_url(url: str, timeout: float) -> Any:
        request = urllib.request.Request(url, method="GET", headers=headers)
        return opener.open(request, timeout=timeout)

    return open_url


class GitHubRefResolver:
    """Resolve refs to commit SHAs with the GitHub commits API."""

    def __init__(
        self,
        url_opener: UrlOpener | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the resolver.

        Args:
          url_opener: Transport; defaults to urllib with the API headers and an
            optional token from the ``GITHUB_TOKEN`` environment variable.
          timeout_seconds: Timeout for the API request.
        """
        if url_opener is None:
            url_opener = _default_url_opener(os.environ.get(GITHUB_TOKEN_ENV))
        self._url_opener = url_opener
        self._timeout_seconds = timeout_seconds

    def resolve(self, repo_url: str, ref: str | None = None) -> str:
        """Return the full commit SHA that ``ref`` points at.

        Args:
          repo_url: Public GitHub repository URL.
          ref: Branch, tag, or commit SHA. None means the default branch.

        Returns:
          The 40-character lowercase commit SHA.

        Raises:
          InvalidRepoUrlError: The repository URL is malformed.
          RepoNotFoundError: The repository does not exist or is private.
          RefNotFoundError: The ref does not name a commit in the repository.
          RepoEmptyError: The repository has no commits.
          RateLimitedError: GitHub refused the request because of rate limits.
          GitHubUnavailableError: GitHub could not be reached or failed.
        """
        coordinate = parse_repo_url(repo_url)
        clean_ref = ref.strip() if ref is not None else ""
        url = _commits_url(coordinate, clean_ref or "HEAD")

        try:
            with self._url_opener(url, self._timeout_seconds) as response:
                body = response.read(_MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            raise _error_for_status(error.code, coordinate, clean_ref) from error
        except TimeoutError as error:
            raise GitHubUnavailableError("GitHub took too long to respond.") from error
        except urllib.error.URLError as error:
            raise GitHubUnavailableError(
                f"GitHub could not be reached: {error.reason}."
            ) from error

        text = body.decode("ascii", errors="replace").strip()
        try:
            return normalize_commit_sha(text)
        except InvalidCommitShaError as error:
            raise GitHubUnavailableError(
                "GitHub returned an unexpected commit reference."
            ) from error


def _commits_url(coordinate: RepoCoordinate, ref: str) -> str:
    """Build the commits API URL for one ref, escaping the ref safely."""
    return (
        f"https://{API_HOST}/repos/{coordinate.owner}/{coordinate.name}"
        f"/commits/{urllib.parse.quote(ref, safe='')}"
    )


def _error_for_status(
    status: int, coordinate: RepoCoordinate, ref: str
) -> Exception:
    """Translate a commits API status into a user-facing error.

    GitHub answers 404 for a missing or private repository, 409 for a
    repository with no commits, and 422 for a ref that names no commit.
    """
    if status == 404:
        return RepoNotFoundError(coordinate.slug)
    if status == 409:
        return RepoEmptyError(coordinate.slug)
    if status == 422 and ref:
        return RefNotFoundError(ref)
    if status in (403, 429):
        return RateLimitedError()
    return GitHubUnavailableError(f"GitHub returned HTTP {status}.")

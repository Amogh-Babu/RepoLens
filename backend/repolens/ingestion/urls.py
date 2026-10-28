"""Validation and construction of repository and archive URLs.

All validation here runs before any network call. Only https URLs on the
GitHub host allowlist are accepted, and only a full commit SHA pins a
snapshot, so a download can never be redirected at an arbitrary host or an
ambiguous ref.
"""

import re
from urllib.parse import urlsplit

from repolens.ingestion.errors import (
    InvalidCommitShaError,
    InvalidRepoUrlError,
    UnsupportedHostError,
)
from repolens.ingestion.models import RepoCoordinate


ALLOWED_REPO_HOSTS = ("github.com", "www.github.com")
CANONICAL_REPO_HOST = "github.com"
ALLOWED_ARCHIVE_HOSTS = ("codeload.github.com",)
ARCHIVE_HOST = "codeload.github.com"
ARCHIVE_FORMAT = "zip"

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_URL_HINT = "Use the format https://github.com/<owner>/<repo>."


def parse_repo_url(raw_url: str) -> RepoCoordinate:
    """Validate a public GitHub repository URL and split it into coordinates.

    Args:
      raw_url: User-supplied repository URL.

    Returns:
      The validated repository coordinate with a normalized host.

    Raises:
      UnsupportedHostError: The URL is well-formed but not on GitHub.
      InvalidRepoUrlError: The URL is empty, not https, carries credentials or
        a query, or does not point at a repository root.
    """
    trimmed = raw_url.strip()
    if not trimmed:
        raise InvalidRepoUrlError(
            message="Enter a GitHub repository URL.", hint=_URL_HINT
        )

    parts = urlsplit(trimmed)
    if parts.scheme.lower() != "https":
        raise InvalidRepoUrlError(
            message="Repository URLs must start with https://.", hint=_URL_HINT
        )
    if parts.query or parts.fragment:
        raise InvalidRepoUrlError(
            message="Repository URLs must not include a query or fragment.",
            hint=_URL_HINT,
        )
    if parts.username is not None or parts.password is not None:
        raise InvalidRepoUrlError(
            message="Repository URLs must not include credentials.",
            hint=_URL_HINT,
        )

    try:
        port = parts.port
    except ValueError:
        raise InvalidRepoUrlError(
            message="This is not a valid repository URL.", hint=_URL_HINT
        ) from None
    if port not in (None, 443):
        raise InvalidRepoUrlError(
            message="Repository URLs must not include a port.", hint=_URL_HINT
        )

    host = (parts.hostname or "").lower()
    if not host:
        raise InvalidRepoUrlError(
            message="This is not a valid repository URL.", hint=_URL_HINT
        )
    if host not in ALLOWED_REPO_HOSTS:
        raise UnsupportedHostError(host)

    owner, name = _split_repo_path(parts.path)
    return RepoCoordinate(host=CANONICAL_REPO_HOST, owner=owner, name=name)


def _split_repo_path(path: str) -> tuple[str, str]:
    """Split a URL path into exactly one owner and one repository name."""
    trimmed_path = path.rstrip("/")
    if trimmed_path.endswith(".git"):
        trimmed_path = trimmed_path[: -len(".git")]

    segments = [segment for segment in trimmed_path.split("/") if segment]
    if len(segments) != 2:
        raise InvalidRepoUrlError(
            message="Link to a repository root, not a file or branch.",
            hint=_URL_HINT,
        )

    owner, name = segments
    if not _OWNER_RE.match(owner) or not _REPO_NAME_RE.match(name):
        raise InvalidRepoUrlError(
            message="This is not a valid GitHub owner and repository name.",
            hint=_URL_HINT,
        )
    if name in (".", ".."):
        raise InvalidRepoUrlError(
            message="This is not a valid GitHub owner and repository name.",
            hint=_URL_HINT,
        )
    return owner, name


def normalize_commit_sha(raw_sha: str) -> str:
    """Validate a full commit SHA and return it lowercased.

    Args:
      raw_sha: Candidate commit SHA.

    Returns:
      The 40-character lowercase SHA.

    Raises:
      InvalidCommitShaError: The value is not a full 40-character hex SHA.
    """
    trimmed = raw_sha.strip()
    if not _FULL_SHA_RE.match(trimmed):
        raise InvalidCommitShaError(trimmed)
    return trimmed.lower()


def build_archive_url(coordinate: RepoCoordinate, sha: str) -> str:
    """Build the GitHub archive URL for one repository pinned at one commit.

    Args:
      coordinate: Validated repository coordinate.
      sha: Commit SHA to pin; validated by ``normalize_commit_sha``.

    Returns:
      An https URL on the GitHub archive host.

    Raises:
      InvalidCommitShaError: The SHA is not a full 40-character hex SHA.
    """
    normalized_sha = normalize_commit_sha(sha)
    return (
        f"https://{ARCHIVE_HOST}/{coordinate.owner}/{coordinate.name}"
        f"/{ARCHIVE_FORMAT}/{normalized_sha}"
    )


def is_allowed_archive_url(url: str) -> bool:
    """Return whether a URL is an https URL on the archive host allowlist."""
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        return False
    if parts.username is not None or parts.password is not None:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False
    return (parts.hostname or "").lower() in ALLOWED_ARCHIVE_HOSTS

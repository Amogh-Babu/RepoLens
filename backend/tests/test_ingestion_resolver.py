"""Tests for resolving refs to commit SHAs with the GitHub commits API."""

import io
import urllib.error

import pytest

from repolens.ingestion import (
    GitHubRefResolver,
    GitHubUnavailableError,
    InvalidRepoUrlError,
    RateLimitedError,
    RefNotFoundError,
    RepoEmptyError,
    RepoNotFoundError,
)


REPO_URL = "https://github.com/octocat/Hello-World"
SHA = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"


class FakeOpener:
    """Records requested URLs and answers with a body or raises an error."""

    def __init__(self, body: bytes = SHA.encode(), error: Exception | None = None):
        self.body = body
        self.error = error
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.github.com", status, "", {}, None)


def test_resolves_the_default_branch_through_head() -> None:
    opener = FakeOpener(body=f"{SHA.upper()}\n".encode())

    sha = GitHubRefResolver(url_opener=opener).resolve(REPO_URL)

    assert sha == SHA
    assert opener.urls == [
        "https://api.github.com/repos/octocat/Hello-World/commits/HEAD"
    ]


def test_escapes_the_ref_in_the_api_url() -> None:
    opener = FakeOpener()

    GitHubRefResolver(url_opener=opener).resolve(REPO_URL, " feature/a b ")

    assert opener.urls == [
        "https://api.github.com/repos/octocat/Hello-World/commits/feature%2Fa%20b"
    ]


def test_blank_ref_means_the_default_branch() -> None:
    opener = FakeOpener()

    GitHubRefResolver(url_opener=opener).resolve(REPO_URL, "   ")

    assert opener.urls[0].endswith("/commits/HEAD")


def test_rejects_an_invalid_url_before_any_request() -> None:
    opener = FakeOpener()

    with pytest.raises(InvalidRepoUrlError):
        GitHubRefResolver(url_opener=opener).resolve("https://gitlab.com/a/b")
    assert opener.urls == []


@pytest.mark.parametrize(
    ("status", "ref", "error_type", "code"),
    [
        (404, None, RepoNotFoundError, "REPO_NOT_FOUND"),
        (409, None, RepoEmptyError, "REPO_EMPTY"),
        (422, "missing", RefNotFoundError, "REF_NOT_FOUND"),
        (403, None, RateLimitedError, "RATE_LIMITED"),
        (429, None, RateLimitedError, "RATE_LIMITED"),
        (500, None, GitHubUnavailableError, "GITHUB_UNAVAILABLE"),
    ],
)
def test_maps_api_statuses_to_errors(status, ref, error_type, code) -> None:
    opener = FakeOpener(error=_http_error(status))

    with pytest.raises(error_type) as caught:
        GitHubRefResolver(url_opener=opener).resolve(REPO_URL, ref)
    assert caught.value.code == code


def test_network_failure_is_github_unavailable() -> None:
    opener = FakeOpener(error=urllib.error.URLError("no route to host"))

    with pytest.raises(GitHubUnavailableError):
        GitHubRefResolver(url_opener=opener).resolve(REPO_URL)


def test_timeout_is_github_unavailable() -> None:
    opener = FakeOpener(error=TimeoutError())

    with pytest.raises(GitHubUnavailableError):
        GitHubRefResolver(url_opener=opener).resolve(REPO_URL)


def test_unexpected_body_is_github_unavailable() -> None:
    opener = FakeOpener(body=b'{"message": "not a sha"}')

    with pytest.raises(GitHubUnavailableError):
        GitHubRefResolver(url_opener=opener).resolve(REPO_URL)

"""Pinned single-file source retrieval for AI summaries."""

import io
import urllib.error

import pytest

from repolens.ai.errors import SourceFetchError, SourceRejectedError
from repolens.ai.source import (
    GitHubRawSourceFetcher,
    _RawHostRedirectHandler,
    build_raw_url,
    decode_source,
    is_allowed_raw_url,
    validate_repo_path,
)
from repolens.ingestion import InvalidCommitShaError, UnsupportedHostError


SHA = "ab" * 20
REPO = "https://github.com/owner/repo"


class Opener:
    def __init__(self, body: bytes = b"x = 1\n", error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> io.BytesIO:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def test_the_url_is_pinned_to_the_commit_on_the_raw_host() -> None:
    url = build_raw_url(REPO, SHA.upper(), "pkg/my module.py")

    assert url == f"https://raw.githubusercontent.com/owner/repo/{SHA}/pkg/my%20module.py"
    assert is_allowed_raw_url(url)


@pytest.mark.parametrize(
    "path",
    [
        "../secrets.py",
        "pkg/../../etc/passwd.py",
        "/etc/passwd.py",
        "pkg//a.py",
        "./a.py",
        "pkg\\a.py",
        "a.py\x00.txt",
        "notes.md",
        "",
        "a" * 401 + ".py",
    ],
)
def test_unsafe_or_unsupported_paths_are_rejected(path: str) -> None:
    with pytest.raises(SourceRejectedError):
        validate_repo_path(path)


def test_only_github_repositories_and_full_shas_are_fetched() -> None:
    with pytest.raises(UnsupportedHostError):
        build_raw_url("https://evil.example.com/owner/repo", SHA, "a.py")
    with pytest.raises(InvalidCommitShaError):
        build_raw_url(REPO, "main", "a.py")


@pytest.mark.parametrize(
    "url, allowed",
    [
        ("https://raw.githubusercontent.com/o/r/sha/a.py", True),
        ("http://raw.githubusercontent.com/o/r/sha/a.py", False),
        ("https://raw.githubusercontent.com:8443/o/r/sha/a.py", False),
        ("https://user@raw.githubusercontent.com/o/r/sha/a.py", False),
        ("https://evil.example.com/a.py", False),
    ],
)
def test_the_raw_host_allowlist(url: str, allowed: bool) -> None:
    assert is_allowed_raw_url(url) is allowed


def test_redirects_off_the_raw_host_are_refused() -> None:
    handler = _RawHostRedirectHandler()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example.com/a.py")


def test_fetch_decodes_utf8_and_strips_a_bom() -> None:
    opener = Opener("﻿name = 'café'\n".encode("utf-8"))

    text = GitHubRawSourceFetcher(url_opener=opener).fetch(REPO, SHA, "a.py")

    assert text == "name = 'café'\n"
    assert opener.urls == [f"https://raw.githubusercontent.com/owner/repo/{SHA}/a.py"]


def test_oversized_binary_and_non_utf8_files_are_rejected() -> None:
    with pytest.raises(SourceRejectedError, match="larger"):
        GitHubRawSourceFetcher(url_opener=Opener(b"x" * 11), max_file_bytes=10).fetch(
            REPO, SHA, "a.py"
        )
    with pytest.raises(SourceRejectedError, match="binary"):
        decode_source(b"\x7fELF\x00\x01")
    with pytest.raises(SourceRejectedError, match="UTF-8"):
        decode_source(b"\xff\xfe\xfa")


@pytest.mark.parametrize(
    "status, code, http_status",
    [(404, "SOURCE_NOT_FOUND", 404), (403, "SOURCE_RATE_LIMITED", 429), (429, "SOURCE_RATE_LIMITED", 429), (500, "SOURCE_UNAVAILABLE", 502)],
)
def test_github_failures_become_summary_errors(status: int, code: str, http_status: int) -> None:
    error = urllib.error.HTTPError("u", status, "x", {}, None)  # type: ignore[arg-type]
    with pytest.raises(SourceFetchError) as caught:
        GitHubRawSourceFetcher(url_opener=Opener(error=error)).fetch(REPO, SHA, "a.py")

    assert (caught.value.code, caught.value.status_code) == (code, http_status)


def test_timeouts_and_unreachable_github_are_reported() -> None:
    with pytest.raises(SourceFetchError) as caught:
        GitHubRawSourceFetcher(url_opener=Opener(error=TimeoutError())).fetch(REPO, SHA, "a.py")
    assert caught.value.status_code == 504
    with pytest.raises(SourceFetchError):
        GitHubRawSourceFetcher(
            url_opener=Opener(error=urllib.error.URLError("down"))
        ).fetch(REPO, SHA, "a.py")


def test_the_default_opener_sends_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    sent: list[dict[str, str]] = []

    class Recorder:
        def open(self, request, timeout):  # noqa: ANN001
            sent.append(dict(request.header_items()))
            return io.BytesIO(b"x = 1\n")

    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: Recorder())
    GitHubRawSourceFetcher().fetch(REPO, SHA, "a.py")

    assert sent and not any("Authorization" in headers for headers in sent)

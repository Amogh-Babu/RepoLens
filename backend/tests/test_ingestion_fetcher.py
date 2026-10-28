"""Unit tests for the HTTPS archive fetcher (#21).

Every test injects a stub URL opener, so no test in this file touches the
network.
"""

from pathlib import Path
from typing import Any
import urllib.error
import pytest

from repolens.ingestion import (
    ArchiveDownloadError,
    ArchiveLimits,
    ArchiveTooLargeError,
    InvalidRepoUrlError,
)
from repolens.ingestion.fetcher import HttpsArchiveFetcher


ARCHIVE_URL = (
    "https://codeload.github.com/octocat/hello-world/zip/"
    "0123456789abcdef0123456789abcdef01234567"
)


class _StubResponse:
    """Minimal stand-in for an ``http.client.HTTPResponse``."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._offset = 0
        self.headers = headers or {}
        self.status = 200

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> "_StubResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _RecordingOpener:
    """URL opener that records its calls and returns a canned response."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float) -> Any:
        self.calls.append((url, timeout))
        if self._error is not None:
            raise self._error
        return self._response


def test_writes_the_archive_to_disk_and_returns_the_byte_count(
    tmp_path: Path,
) -> None:
    body = b"PK\x03\x04 archive bytes"
    opener = _RecordingOpener(_StubResponse(body))
    fetcher = HttpsArchiveFetcher(url_opener=opener)
    destination = tmp_path / "repo.zip"

    written = fetcher.fetch(ARCHIVE_URL, destination)

    assert written == len(body)
    assert destination.read_bytes() == body


def test_uses_the_configured_timeout(tmp_path: Path) -> None:
    opener = _RecordingOpener(_StubResponse(b"zip"))
    fetcher = HttpsArchiveFetcher(
        limits=ArchiveLimits(timeout_seconds=7.5), url_opener=opener
    )

    fetcher.fetch(ARCHIVE_URL, tmp_path / "repo.zip")

    assert opener.calls == [(ARCHIVE_URL, 7.5)]


@pytest.mark.parametrize(
    "url",
    [
        "http://codeload.github.com/octocat/hello-world/zip/main",
        "https://evil.example/octocat/hello-world/zip/main",
        "https://github.com/octocat/hello-world/archive/main.zip",
        "file:///etc/passwd",
        "https://user:token@codeload.github.com/o/r/zip/main",
    ],
)
def test_refuses_urls_off_the_archive_host_allowlist_without_opening_them(
    tmp_path: Path, url: str
) -> None:
    opener = _RecordingOpener(_StubResponse(b"zip"))
    fetcher = HttpsArchiveFetcher(url_opener=opener)
    destination = tmp_path / "repo.zip"

    with pytest.raises(InvalidRepoUrlError):
        fetcher.fetch(url, destination)

    assert opener.calls == []
    assert not destination.exists()


def test_rejects_an_archive_whose_content_length_exceeds_the_cap(
    tmp_path: Path,
) -> None:
    opener = _RecordingOpener(
        _StubResponse(b"x" * 10, headers={"Content-Length": "10"})
    )
    fetcher = HttpsArchiveFetcher(
        limits=ArchiveLimits(max_archive_bytes=4), url_opener=opener
    )
    destination = tmp_path / "repo.zip"

    with pytest.raises(ArchiveTooLargeError) as excinfo:
        fetcher.fetch(ARCHIVE_URL, destination)

    assert excinfo.value.code == "ARCHIVE_TOO_LARGE"
    assert not destination.exists()


def test_stops_and_cleans_up_when_the_body_outgrows_the_cap(tmp_path: Path) -> None:
    """A missing or dishonest Content-Length must not defeat the cap."""
    opener = _RecordingOpener(_StubResponse(b"x" * 5000))
    fetcher = HttpsArchiveFetcher(
        limits=ArchiveLimits(max_archive_bytes=128), url_opener=opener
    )
    destination = tmp_path / "repo.zip"

    with pytest.raises(ArchiveTooLargeError):
        fetcher.fetch(ARCHIVE_URL, destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    "status, expected_status_code, expected_text",
    [
        (404, 404, "not found"),
        (403, 429, "rate"),
        (429, 429, "rate"),
        (500, 502, "github"),
    ],
)
def test_maps_http_errors_to_clear_download_errors(
    tmp_path: Path, status: int, expected_status_code: int, expected_text: str
) -> None:
    error = urllib.error.HTTPError(ARCHIVE_URL, status, "boom", {}, None)  # type: ignore[arg-type]
    fetcher = HttpsArchiveFetcher(url_opener=_RecordingOpener(error=error))
    destination = tmp_path / "repo.zip"

    with pytest.raises(ArchiveDownloadError) as excinfo:
        fetcher.fetch(ARCHIVE_URL, destination)

    assert excinfo.value.code == "DOWNLOAD_FAILED"
    assert excinfo.value.status_code == expected_status_code
    assert expected_text in excinfo.value.message.lower()
    assert not destination.exists()


def test_maps_network_failures_to_download_errors(tmp_path: Path) -> None:
    error = urllib.error.URLError("connection reset")
    fetcher = HttpsArchiveFetcher(url_opener=_RecordingOpener(error=error))

    with pytest.raises(ArchiveDownloadError):
        fetcher.fetch(ARCHIVE_URL, tmp_path / "repo.zip")


def test_maps_timeouts_to_download_errors(tmp_path: Path) -> None:
    fetcher = HttpsArchiveFetcher(url_opener=_RecordingOpener(error=TimeoutError()))

    with pytest.raises(ArchiveDownloadError) as excinfo:
        fetcher.fetch(ARCHIVE_URL, tmp_path / "repo.zip")

    assert "timed out" in excinfo.value.message.lower()


def test_redirects_off_the_allowlist_are_refused() -> None:
    from repolens.ingestion.fetcher import AllowlistedRedirectHandler

    handler = AllowlistedRedirectHandler()

    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            req=None,
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="https://evil.example/payload.zip",
        )

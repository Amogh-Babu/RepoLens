"""Unit tests for GitHubSource snapshot downloads (#21).

The archive fetcher is stubbed with a local zip, so these tests make no
network calls and never run repository code.
"""

from pathlib import Path
import io
import sys
import zipfile

import pytest

from repolens.ingestion import (
    ArchiveDownloadError,
    DestinationNotEmptyError,
    InvalidCommitShaError,
    InvalidRepoUrlError,
    Snapshot,
    UnsafeArchiveError,
    UnsupportedHostError,
)
from repolens.ingestion.source import GitHubSource


REPO_URL = "https://github.com/octocat/hello-world"
SHA = "0123456789abcdef0123456789abcdef01234567"
PREFIX = f"hello-world-{SHA}"
ARCHIVE_URL = f"https://codeload.github.com/octocat/hello-world/zip/{SHA}"


def _zip_bytes(entries: dict[str, str]) -> bytes:
    """Build an in-memory zip archive with the given entries."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class _StubFetcher:
    """Archive fetcher that writes prepared bytes instead of downloading."""

    def __init__(self, payload: bytes = b"", error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.calls: list[tuple[str, Path]] = []

    def fetch(self, url: str, destination: Path) -> int:
        self.calls.append((url, destination))
        if self._error is not None:
            raise self._error
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._payload)
        return len(self._payload)


def _repo_fetcher() -> _StubFetcher:
    return _StubFetcher(
        _zip_bytes(
            {
                f"{PREFIX}/README.md": "# hello\n",
                f"{PREFIX}/app/__init__.py": "",
                f"{PREFIX}/app/main.py": "VALUE = 1\n",
            }
        )
    )


def test_downloads_and_extracts_the_snapshot_to_disk(tmp_path: Path) -> None:
    source = GitHubSource(fetcher=_repo_fetcher())
    destination = tmp_path / "snapshot"

    snapshot = source.fetch_snapshot(REPO_URL, SHA, destination)

    assert snapshot == Snapshot(
        repo=REPO_URL,
        sha=SHA,
        root=str(destination),
        files=("README.md", "app/__init__.py", "app/main.py"),
    )
    assert snapshot.file_count == 3
    assert (destination / "README.md").read_text() == "# hello\n"
    assert (destination / "app" / "main.py").read_text() == "VALUE = 1\n"


def test_requests_the_archive_url_pinned_to_the_commit(tmp_path: Path) -> None:
    fetcher = _repo_fetcher()
    source = GitHubSource(fetcher=fetcher)

    source.fetch_snapshot(f"{REPO_URL}.git", SHA.upper(), tmp_path / "snapshot")

    assert [url for url, _ in fetcher.calls] == [ARCHIVE_URL]


def test_normalizes_the_repo_url_and_sha_in_the_snapshot(tmp_path: Path) -> None:
    source = GitHubSource(fetcher=_repo_fetcher())

    snapshot = source.fetch_snapshot(
        "https://www.github.com/octocat/hello-world.git/", SHA.upper(), tmp_path / "s"
    )

    assert snapshot.repo == REPO_URL
    assert snapshot.sha == SHA


def test_deletes_the_downloaded_archive_after_extracting(tmp_path: Path) -> None:
    fetcher = _repo_fetcher()
    source = GitHubSource(fetcher=fetcher)
    destination = tmp_path / "snapshot"

    snapshot = source.fetch_snapshot(REPO_URL, SHA, destination)

    archive_path = fetcher.calls[0][1]
    assert not archive_path.exists()
    assert not archive_path.parent.exists()
    extracted = sorted(
        str(path.relative_to(destination))
        for path in destination.rglob("*")
        if path.is_file()
    )
    assert extracted == list(snapshot.files)


def test_does_not_import_or_execute_repository_code(tmp_path: Path) -> None:
    """The snapshot is data on disk; nothing in it is imported or run."""
    sentinel = tmp_path / "executed.txt"
    payload = _zip_bytes(
        {
            f"{PREFIX}/evil/__init__.py": "",
            f"{PREFIX}/evil/boom.py": (
                "import pathlib\n"
                f"pathlib.Path({str(sentinel)!r}).write_text('executed')\n"
            ),
            f"{PREFIX}/setup.py": (
                "import pathlib\n"
                f"pathlib.Path({str(sentinel)!r}).write_text('executed')\n"
            ),
        }
    )
    source = GitHubSource(fetcher=_StubFetcher(payload))
    destination = tmp_path / "snapshot"

    snapshot = source.fetch_snapshot(REPO_URL, SHA, destination)

    assert "evil.boom" not in sys.modules
    assert not sentinel.exists()
    assert "evil/boom.py" in snapshot.files
    assert (destination / "evil" / "boom.py").is_file()


@pytest.mark.parametrize(
    "repo_url, error_type",
    [
        ("", InvalidRepoUrlError),
        ("not a url", InvalidRepoUrlError),
        ("http://github.com/octocat/hello-world", InvalidRepoUrlError),
        ("https://github.com/octocat/hello-world/tree/main", InvalidRepoUrlError),
        ("https://gitlab.com/octocat/hello-world", UnsupportedHostError),
    ],
)
def test_rejects_bad_urls_before_downloading_anything(
    tmp_path: Path, repo_url: str, error_type: type[Exception]
) -> None:
    fetcher = _repo_fetcher()
    source = GitHubSource(fetcher=fetcher)
    destination = tmp_path / "snapshot"

    with pytest.raises(error_type):
        source.fetch_snapshot(repo_url, SHA, destination)

    assert fetcher.calls == []
    assert not destination.exists()


@pytest.mark.parametrize("sha", ["", "main", "0123456", SHA + "0"])
def test_rejects_bad_shas_before_downloading_anything(
    tmp_path: Path, sha: str
) -> None:
    fetcher = _repo_fetcher()
    source = GitHubSource(fetcher=fetcher)
    destination = tmp_path / "snapshot"

    with pytest.raises(InvalidCommitShaError):
        source.fetch_snapshot(REPO_URL, sha, destination)

    assert fetcher.calls == []
    assert not destination.exists()


def test_refuses_to_extract_over_an_existing_snapshot(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot"
    destination.mkdir()
    existing = destination / "keep.txt"
    existing.write_text("keep me\n")
    fetcher = _repo_fetcher()
    source = GitHubSource(fetcher=fetcher)

    with pytest.raises(DestinationNotEmptyError) as excinfo:
        source.fetch_snapshot(REPO_URL, SHA, destination)

    assert excinfo.value.code == "DESTINATION_NOT_EMPTY"
    assert fetcher.calls == []
    assert existing.read_text() == "keep me\n"


def test_discards_the_partial_snapshot_when_extraction_fails(tmp_path: Path) -> None:
    payload = _zip_bytes(
        {f"{PREFIX}/ok.py": "x = 1\n", "../escaped.py": "pwned = True\n"}
    )
    source = GitHubSource(fetcher=_StubFetcher(payload))
    destination = tmp_path / "snapshot"

    with pytest.raises(UnsafeArchiveError):
        source.fetch_snapshot(REPO_URL, SHA, destination)

    assert not destination.exists()
    assert not (tmp_path / "escaped.py").exists()


def test_propagates_download_failures_without_leaving_a_snapshot(
    tmp_path: Path,
) -> None:
    fetcher = _StubFetcher(error=ArchiveDownloadError("GitHub is unreachable."))
    source = GitHubSource(fetcher=fetcher)
    destination = tmp_path / "snapshot"

    with pytest.raises(ArchiveDownloadError):
        source.fetch_snapshot(REPO_URL, SHA, destination)

    assert not destination.exists()
    assert not fetcher.calls[0][1].parent.exists()

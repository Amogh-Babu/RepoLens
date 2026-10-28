"""Unit tests for safe archive extraction (#21).

The archives here are built in-memory; no network calls and no repository code
are ever run.
"""

from pathlib import Path
import stat
import zipfile

import pytest

from repolens.ingestion import (
    ArchiveFormatError,
    ArchiveLimits,
    ArchiveTooLargeError,
    UnsafeArchiveError,
)
from repolens.ingestion.archive import extract_zip_archive


PREFIX = "hello-world-0123456789abcdef0123456789abcdef01234567"


def _write_zip(
    path: Path,
    entries: dict[str, str],
    *,
    directories: tuple[str, ...] = (),
) -> Path:
    """Write a zip archive containing the given file and directory entries."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in directories:
            archive.writestr(zipfile.ZipInfo(name), "")
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def _write_symlink_zip(path: Path, name: str, target: str) -> Path:
    """Write a zip archive whose only entry is a Unix symlink."""
    info = zipfile.ZipInfo(name)
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, target)
    return path


def test_extracts_files_to_disk_and_strips_the_github_prefix(tmp_path: Path) -> None:
    archive = _write_zip(
        tmp_path / "repo.zip",
        {
            f"{PREFIX}/README.md": "# hello\n",
            f"{PREFIX}/app/__init__.py": "",
            f"{PREFIX}/app/main.py": "print('never run')\n",
        },
        directories=(f"{PREFIX}/", f"{PREFIX}/app/"),
    )
    destination = tmp_path / "snapshot"

    files = extract_zip_archive(archive, destination)

    assert files == ("README.md", "app/__init__.py", "app/main.py")
    assert (destination / "README.md").read_text() == "# hello\n"
    assert (destination / "app" / "main.py").read_text() == "print('never run')\n"


def test_creates_the_destination_directory(tmp_path: Path) -> None:
    archive = _write_zip(tmp_path / "repo.zip", {f"{PREFIX}/a.py": "a = 1\n"})
    destination = tmp_path / "nested" / "snapshot"

    extract_zip_archive(archive, destination)

    assert destination.is_dir()


def test_keeps_root_level_entries_when_there_is_no_single_prefix(
    tmp_path: Path,
) -> None:
    archive = _write_zip(
        tmp_path / "repo.zip", {"README.md": "x\n", "pkg/mod.py": "y\n"}
    )
    destination = tmp_path / "snapshot"

    files = extract_zip_archive(archive, destination)

    assert files == ("README.md", "pkg/mod.py")


def test_keeps_prefixes_when_several_top_level_entries_exist(tmp_path: Path) -> None:
    archive = _write_zip(
        tmp_path / "repo.zip", {"one/a.py": "a\n", "two/b.py": "b\n"}
    )
    destination = tmp_path / "snapshot"

    files = extract_zip_archive(archive, destination)

    assert files == ("one/a.py", "two/b.py")


@pytest.mark.parametrize(
    "member_name",
    [
        "../escaped.py",
        f"{PREFIX}/../../escaped.py",
        f"{PREFIX}/app/../../../escaped.py",
        "..",
        "subdir/../../escaped.py",
    ],
)
def test_rejects_path_traversal_members(tmp_path: Path, member_name: str) -> None:
    archive = _write_zip(tmp_path / "repo.zip", {member_name: "pwned = True\n"})
    destination = tmp_path / "snapshot"

    with pytest.raises(UnsafeArchiveError) as excinfo:
        extract_zip_archive(archive, destination)

    assert excinfo.value.code == "UNSAFE_ARCHIVE"
    assert not (tmp_path / "escaped.py").exists()
    assert not (tmp_path / "snapshot.py").exists()


@pytest.mark.parametrize(
    "member_name",
    [
        "/etc/passwd",
        "//etc/passwd",
        "C:/Windows/system32/evil.dll",
        "C:\\Windows\\evil.dll",
        "app\\..\\..\\escaped.py",
        "\\\\server\\share\\evil.dll",
    ],
)
def test_rejects_absolute_and_windows_style_members(
    tmp_path: Path, member_name: str
) -> None:
    archive = _write_zip(tmp_path / "repo.zip", {member_name: "pwned = True\n"})
    destination = tmp_path / "snapshot"

    with pytest.raises(UnsafeArchiveError):
        extract_zip_archive(archive, destination)


def test_rejects_symlink_members(tmp_path: Path) -> None:
    archive = _write_symlink_zip(
        tmp_path / "repo.zip", f"{PREFIX}/link.py", "/etc/passwd"
    )
    destination = tmp_path / "snapshot"

    with pytest.raises(UnsafeArchiveError) as excinfo:
        extract_zip_archive(archive, destination)

    assert "symlink" in excinfo.value.reason
    assert not (destination / "link.py").exists()


def test_rejects_non_regular_members(tmp_path: Path) -> None:
    info = zipfile.ZipInfo(f"{PREFIX}/fifo")
    info.external_attr = (stat.S_IFIFO | 0o644) << 16
    archive_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "")

    with pytest.raises(UnsafeArchiveError):
        extract_zip_archive(archive_path, tmp_path / "snapshot")


def test_rejects_archives_with_too_many_files(tmp_path: Path) -> None:
    archive = _write_zip(
        tmp_path / "repo.zip",
        {f"{PREFIX}/f{index}.py": "x\n" for index in range(5)},
    )

    with pytest.raises(ArchiveTooLargeError) as excinfo:
        extract_zip_archive(
            archive, tmp_path / "snapshot", ArchiveLimits(max_file_count=3)
        )

    assert excinfo.value.code == "ARCHIVE_TOO_LARGE"


def test_rejects_archives_that_expand_past_the_size_cap(tmp_path: Path) -> None:
    archive = _write_zip(
        tmp_path / "repo.zip", {f"{PREFIX}/big.py": "A" * 5000}
    )

    with pytest.raises(ArchiveTooLargeError):
        extract_zip_archive(
            archive, tmp_path / "snapshot", ArchiveLimits(max_extracted_bytes=100)
        )


def test_rejects_bytes_that_are_not_a_zip_archive(tmp_path: Path) -> None:
    archive = tmp_path / "repo.zip"
    archive.write_bytes(b"this is not a zip archive")

    with pytest.raises(ArchiveFormatError) as excinfo:
        extract_zip_archive(archive, tmp_path / "snapshot")

    assert excinfo.value.code == "INVALID_ARCHIVE"


def test_rejects_archives_that_contain_no_files(tmp_path: Path) -> None:
    archive = _write_zip(tmp_path / "repo.zip", {}, directories=(f"{PREFIX}/",))

    with pytest.raises(ArchiveFormatError):
        extract_zip_archive(archive, tmp_path / "snapshot")


def _write_encrypted_flag_zip(path: Path, name: str) -> Path:
    """Write a zip archive whose entry claims to be encrypted.

    ``zipfile`` clears the encryption flag when writing, so bit 0 of the
    general purpose flags is set directly in the local and central headers.
    """
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, "x = 1\n")
    data = bytearray(path.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        header_start = data.index(signature)
        data[header_start + flag_offset] |= 0x1
    path.write_bytes(bytes(data))
    return path


def test_rejects_encrypted_members_before_reading_them(tmp_path: Path) -> None:
    archive_path = _write_encrypted_flag_zip(
        tmp_path / "repo.zip", f"{PREFIX}/secret.py"
    )

    with pytest.raises(UnsafeArchiveError) as excinfo:
        extract_zip_archive(archive_path, tmp_path / "snapshot")

    assert "encrypted" in excinfo.value.reason


def test_rejects_empty_member_names(tmp_path: Path) -> None:
    archive_path = tmp_path / "repo.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(zipfile.ZipInfo(""), "x = 1\n")

    with pytest.raises(UnsafeArchiveError):
        extract_zip_archive(archive_path, tmp_path / "snapshot")

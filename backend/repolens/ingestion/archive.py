"""Safe extraction of repository archives.

Archive members are untrusted input. Every entry is validated before a single
byte is written: names must be relative and free of traversal components, and
only plain files and directories are created. Archive content is written to
disk and never imported, executed, or evaluated.
"""

from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from repolens.ingestion.errors import (
    ArchiveFormatError,
    ArchiveTooLargeError,
    UnsafeArchiveError,
)
from repolens.ingestion.models import ArchiveLimits


_COPY_CHUNK_BYTES = 64 * 1024
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_DEFAULT_LIMITS = ArchiveLimits()


def extract_zip_archive(
    archive_path: Path,
    destination: Path,
    limits: ArchiveLimits = _DEFAULT_LIMITS,
) -> tuple[str, ...]:
    """Extract a zip archive into a destination directory.

    A single shared top-level directory, as used by GitHub archives
    (``<repo>-<sha>/``), is stripped so files land at the destination root.

    Args:
      archive_path: Path to the downloaded zip archive.
      destination: Directory to extract into; created if missing.
      limits: Size and count caps applied while extracting.

    Returns:
      Sorted repository-relative POSIX paths of the extracted files.

    Raises:
      ArchiveFormatError: The file is not a readable zip, or holds no files.
      UnsafeArchiveError: A member escapes the destination or is not a plain
        file or directory.
      ArchiveTooLargeError: The archive holds too many files or expands past
        the configured byte cap.
    """
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            file_members, directory_names = _plan_extraction(members, limits)
            return _write_members(
                archive, file_members, directory_names, destination, limits
            )
    except zipfile.BadZipFile as error:
        raise ArchiveFormatError(
            f"The downloaded archive is not a readable zip file: {error}."
        ) from error


def _plan_extraction(
    members: list[zipfile.ZipInfo],
    limits: ArchiveLimits,
) -> tuple[tuple[tuple[zipfile.ZipInfo, str], ...], tuple[str, ...]]:
    """Validate every member and resolve its destination-relative path."""
    file_paths: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    directory_paths: list[PurePosixPath] = []
    for member in members:
        relative = _safe_relative_path(member)
        if _is_directory(member):
            directory_paths.append(relative)
        else:
            file_paths.append((member, relative))

    if not file_paths:
        raise ArchiveFormatError("The downloaded archive contains no files.")
    if len(file_paths) > limits.max_file_count:
        raise ArchiveTooLargeError(
            f"The archive contains {len(file_paths)} files, "
            f"more than the {limits.max_file_count} file limit."
        )

    declared_bytes = sum(member.file_size for member, _ in file_paths)
    if declared_bytes > limits.max_extracted_bytes:
        raise ArchiveTooLargeError(
            f"The archive expands to {declared_bytes} bytes, "
            f"more than the {limits.max_extracted_bytes} byte limit."
        )

    prefix = _common_top_level_directory(
        [relative for _, relative in file_paths], directory_paths
    )
    planned_files = tuple(
        (member, _strip_prefix(relative, prefix)) for member, relative in file_paths
    )
    planned_directories = tuple(
        stripped
        for stripped in (
            _strip_prefix(relative, prefix) for relative in directory_paths
        )
        if stripped
    )
    return planned_files, planned_directories


def _is_directory(member: zipfile.ZipInfo) -> bool:
    """Return whether a member is a directory entry."""
    mode = member.external_attr >> 16
    return member.is_dir() or stat.S_ISDIR(mode)


def _safe_relative_path(member: zipfile.ZipInfo) -> PurePosixPath:
    """Return a member's relative path, rejecting anything unsafe.

    Raises:
      UnsafeArchiveError: The name is empty, absolute, uses Windows
        separators, contains a traversal component, or the entry is encrypted
        or not a plain file or directory.
    """
    name = member.filename
    if member.flag_bits & 0x1:
        raise UnsafeArchiveError(name, "encrypted entries are not supported")

    _reject_unsupported_type(member, name)

    if not name or not name.strip("/"):
        raise UnsafeArchiveError(name, "the entry name is empty")
    if "\\" in name:
        raise UnsafeArchiveError(name, "Windows path separators are not allowed")
    if name.startswith("/") or _WINDOWS_DRIVE_RE.match(name):
        raise UnsafeArchiveError(name, "absolute paths are not allowed")
    if "\x00" in name:
        raise UnsafeArchiveError(name, "the entry name contains a null byte")

    parts = [part for part in name.split("/") if part]
    if any(part == ".." for part in parts):
        raise UnsafeArchiveError(name, "path traversal is not allowed")

    relative = PurePosixPath(*[part for part in parts if part != "."])
    if not relative.parts:
        raise UnsafeArchiveError(name, "the entry name is empty")
    return relative


def _reject_unsupported_type(member: zipfile.ZipInfo, name: str) -> None:
    """Reject symlinks, devices, and every other non-plain entry type.

    Archives written without Unix mode bits store a file type of zero; those
    entries are treated as plain files.
    """
    file_type = stat.S_IFMT(member.external_attr >> 16)
    if file_type == stat.S_IFLNK:
        raise UnsafeArchiveError(name, "symlink entries are not allowed")
    if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise UnsafeArchiveError(name, "only files and directories are allowed")


def _common_top_level_directory(
    file_paths: list[PurePosixPath],
    directory_paths: list[PurePosixPath],
) -> str:
    """Return the single wrapper directory shared by all files, if any."""
    if any(len(path.parts) < 2 for path in file_paths):
        return ""
    top_levels = {path.parts[0] for path in file_paths}
    top_levels.update(
        path.parts[0] for path in directory_paths if path.parts
    )
    if len(top_levels) != 1:
        return ""
    return top_levels.pop()


def _strip_prefix(relative: PurePosixPath, prefix: str) -> str:
    """Remove the shared wrapper directory from a member path."""
    if not prefix:
        return relative.as_posix()
    parts = relative.parts
    if not parts or parts[0] != prefix:
        return relative.as_posix()
    return PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""


def _write_members(
    archive: zipfile.ZipFile,
    file_members: tuple[tuple[zipfile.ZipInfo, str], ...],
    directory_names: tuple[str, ...],
    destination: Path,
    limits: ArchiveLimits,
) -> tuple[str, ...]:
    """Write validated members to disk, enforcing the extracted byte cap."""
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()

    for directory_name in directory_names:
        _resolve_inside(resolved_destination, directory_name).mkdir(
            parents=True, exist_ok=True
        )

    written_bytes = 0
    extracted: list[str] = []
    for member, relative_path in file_members:
        target = _resolve_inside(resolved_destination, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as sink:
            while chunk := source.read(_COPY_CHUNK_BYTES):
                written_bytes += len(chunk)
                if written_bytes > limits.max_extracted_bytes:
                    raise ArchiveTooLargeError(
                        "The archive expands past the "
                        f"{limits.max_extracted_bytes} byte limit."
                    )
                sink.write(chunk)
        extracted.append(relative_path)

    return tuple(sorted(extracted))


def _resolve_inside(resolved_destination: Path, relative_path: str) -> Path:
    """Resolve a relative member path and confirm it stays under destination.

    This repeats the name checks in ``_safe_relative_path`` against the
    resolved filesystem path, so an unexpected name form still cannot write
    outside the snapshot directory.
    """
    target = (resolved_destination / relative_path).resolve()
    if target != resolved_destination and not target.is_relative_to(
        resolved_destination
    ):
        raise UnsafeArchiveError(relative_path, "the entry escapes the snapshot")
    return target

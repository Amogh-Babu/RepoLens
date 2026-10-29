"""Exclusion rules that keep non-reviewable files out of the analysis.

A snapshot usually holds more than the repository's own code: checked-in
dependencies, build output, generated bindings, lock files, and the occasional
multi-megabyte data file. Analyzing those bloats the dependency graph and the
search index with results nobody is looking for, so they are filtered out
before any analyzer sees them, and a repository whose remaining source still
exceeds the caps in `ArchiveLimits` is rejected with a clear error.

Decisions are made from a repository-relative path and a file size only. No
file is opened, imported, executed, or evaluated here.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from repolens.ingestion.errors import FileTooLargeError, RepositoryTooLargeError
from repolens.ingestion.models import ArchiveLimits, Snapshot


ExclusionReason = Literal["metadata", "vendored", "generated", "too_large"]

# Version-control and tooling directories: machine state, never source.
METADATA_DIRECTORY_NAMES = frozenset(
    {
        ".bzr",
        ".cache",
        ".git",
        ".gradle",
        ".hg",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".terraform",
        ".tox",
        ".vscode",
        "__pycache__",
    }
)

# Directories holding third-party code checked into the repository.
VENDORED_DIRECTORY_NAMES = frozenset(
    {
        ".eggs",
        ".venv",
        "bower_components",
        "carthage",
        "eggs",
        "jspm_packages",
        "node_modules",
        "pods",
        "site-packages",
        "third_party",
        "thirdparty",
        "vendor",
        "vendored",
        "venv",
        "virtualenv",
    }
)

# Directories holding build output or other generated artifacts.
GENERATED_DIRECTORY_NAMES = frozenset(
    {
        ".next",
        ".nuxt",
        ".parcel-cache",
        ".serverless",
        ".svelte-kit",
        "__generated__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "target",
    }
)

# Dependency lock files and other whole-file generated manifests.
GENERATED_FILE_NAMES = frozenset(
    {
        "cargo.lock",
        "composer.lock",
        "gemfile.lock",
        "go.sum",
        "mix.lock",
        "npm-shrinkwrap.json",
        "package-lock.json",
        "packages.lock.json",
        "pipfile.lock",
        "pnpm-lock.yaml",
        "podfile.lock",
        "poetry.lock",
        "pubspec.lock",
        "yarn.lock",
    }
)

# Name endings that mark a file as compiled, minified, or code-generated.
GENERATED_FILE_SUFFIXES = (
    ".css.map",
    ".designer.cs",
    ".freezed.dart",
    ".g.cs",
    ".g.dart",
    ".generated.go",
    ".generated.js",
    ".generated.py",
    ".generated.ts",
    ".js.map",
    ".min.css",
    ".min.js",
    ".min.mjs",
    ".mjs.map",
    ".pb.cc",
    ".pb.go",
    ".pb.h",
    ".pyc",
    ".pyo",
    "_generated.go",
    "_generated.py",
    "_generated.ts",
    "_pb.d.ts",
    "_pb.js",
    "_pb2.py",
    "_pb2.pyi",
    "_pb2_grpc.py",
)

# Directory name endings that mark a generated packaging directory.
GENERATED_DIRECTORY_SUFFIXES = (".egg-info", ".dsym")


@dataclass(frozen=True)
class FileExclusion:
    """Why one file is not analyzed."""

    path: str
    reason: ExclusionReason
    detail: str

    @property
    def message(self) -> str:
        """Return a single-line explanation for logs and API responses."""
        return f"{self.path}: {self.detail}"


@dataclass(frozen=True)
class FilterReport:
    """The analyzable files of one snapshot, and what was left out."""

    analyzable_paths: tuple[str, ...] = ()
    exclusions: tuple[FileExclusion, ...] = ()
    analyzable_bytes: int = 0

    @property
    def analyzable_count(self) -> int:
        """Return the number of files that are analyzed."""
        return len(self.analyzable_paths)

    @property
    def excluded_paths(self) -> tuple[str, ...]:
        """Return the paths that are not analyzed, in report order."""
        return tuple(exclusion.path for exclusion in self.exclusions)

    @property
    def excluded_count(self) -> int:
        """Return the number of files that are not analyzed."""
        return len(self.exclusions)

    def exclusion_for(self, path: str) -> FileExclusion | None:
        """Return the exclusion recorded for `path`, or None if it is analyzed."""
        for exclusion in self.exclusions:
            if exclusion.path == path:
                return exclusion
        return None


class SourceFileFilter:
    """Decide which snapshot files are the repository's own reviewable source.

    Implements the `FileFilter` port. Instances hold no per-repository state,
    so one filter can be shared by the ingestion pipeline and the analysis
    service.
    """

    def __init__(
        self,
        limits: ArchiveLimits = ArchiveLimits(),
        extra_excluded_directories: Iterable[str] = (),
        extra_excluded_suffixes: Iterable[str] = (),
    ) -> None:
        """Initialize the filter.

        Args:
          limits: Caps for one file and for a whole repository's source.
          extra_excluded_directories: Additional directory names to exclude,
            matched case-insensitively against every path component.
          extra_excluded_suffixes: Additional file name endings to treat as
            generated, matched case-insensitively.
        """
        self._limits = limits
        self._extra_directories = frozenset(
            name.strip("/").lower() for name in extra_excluded_directories if name
        )
        self._extra_suffixes = tuple(
            suffix.lower() for suffix in extra_excluded_suffixes if suffix
        )

    @property
    def limits(self) -> ArchiveLimits:
        """Return the size caps this filter applies."""
        return self._limits

    def exclusion_for(
        self, path: str, size_bytes: int | None = None
    ) -> FileExclusion | None:
        """Return why `path` is not analyzed, or None when it should be.

        Args:
          path: Repository-relative POSIX path of a file.
          size_bytes: Size of the file, when known. The per-file cap is only
            applied when a size is given.
        """
        components = _path_components(path)
        if not components:
            return None

        directory_exclusion = self._directory_exclusion(path, components[:-1])
        if directory_exclusion is not None:
            return directory_exclusion

        name_exclusion = self._name_exclusion(path, components[-1])
        if name_exclusion is not None:
            return name_exclusion

        if size_bytes is not None and size_bytes > self._limits.max_file_bytes:
            return FileExclusion(
                path=path,
                reason="too_large",
                detail=(
                    f"{size_bytes} bytes is more than the "
                    f"{self._limits.max_file_bytes} byte per-file limit"
                ),
            )
        return None

    def directory_exclusion_for(self, path: str) -> FileExclusion | None:
        """Return why the directory at `path` is not analyzed, or None.

        Tree walks use this to prune a vendored or generated directory instead
        of visiting every file inside it.
        """
        components = _path_components(path)
        if not components:
            return None
        return self._directory_exclusion(path, components)

    def should_analyze(self, path: str, size_bytes: int | None = None) -> bool:
        """Return whether `path` is analyzed rather than filtered out."""
        return self.exclusion_for(path, size_bytes) is None

    def require_file_within_limits(self, path: str, size_bytes: int) -> None:
        """Raise if one requested file is larger than the per-file cap.

        Snapshot filtering skips an oversized file rather than failing, so this
        is for callers that asked for one named file and need to be told why it
        is not analyzed.

        Raises:
          FileTooLargeError: `size_bytes` exceeds `limits.max_file_bytes`.
        """
        if size_bytes > self._limits.max_file_bytes:
            raise FileTooLargeError(
                path=path,
                size_bytes=size_bytes,
                max_bytes=self._limits.max_file_bytes,
            )

    def filter_files(self, files: Iterable[tuple[str, int]]) -> FilterReport:
        """Split (path, size) pairs into analyzable files and exclusions.

        Args:
          files: Repository-relative POSIX paths with their sizes in bytes.

        Returns:
          The analyzable paths in input order, every exclusion and its reason,
          and the total analyzable bytes.

        Raises:
          RepositoryTooLargeError: The analyzable files exceed
            `limits.max_analyzable_file_count` or `limits.max_analyzable_bytes`.
            Both are checked while the files are read, so an oversized
            repository is rejected without measuring all of it.
        """
        analyzable: list[str] = []
        exclusions: list[FileExclusion] = []
        analyzable_bytes = 0

        for path, size_bytes in files:
            exclusion = self.exclusion_for(path, size_bytes)
            if exclusion is not None:
                exclusions.append(exclusion)
                continue
            analyzable.append(path)
            analyzable_bytes += size_bytes
            self._require_repository_within_limits(len(analyzable), analyzable_bytes)

        return FilterReport(
            analyzable_paths=tuple(analyzable),
            exclusions=tuple(exclusions),
            analyzable_bytes=analyzable_bytes,
        )

    def filter_snapshot(self, snapshot: Snapshot) -> FilterReport:
        """Filter an extracted snapshot's files, sizing each one on disk.

        A listed file that is no longer a readable regular file is left out of
        the report rather than failing the whole filter.

        Raises:
          RepositoryTooLargeError: The snapshot's analyzable source exceeds the
            repository caps.
        """
        return self.filter_files(_sized_paths(Path(snapshot.root), snapshot.files))

    def _require_repository_within_limits(
        self, analyzable_count: int, analyzable_bytes: int
    ) -> None:
        """Raise once the analyzable source passes a repository-wide cap."""
        if analyzable_count > self._limits.max_analyzable_file_count:
            raise RepositoryTooLargeError(
                "This repository has more than "
                f"{self._limits.max_analyzable_file_count} source files to "
                "analyze, past the file limit."
            )
        if analyzable_bytes > self._limits.max_analyzable_bytes:
            raise RepositoryTooLargeError(
                "This repository holds more than "
                f"{self._limits.max_analyzable_bytes} bytes of source to "
                "analyze, past the size limit."
            )

    def _directory_exclusion(
        self, path: str, components: tuple[str, ...]
    ) -> FileExclusion | None:
        """Return the first exclusion a directory component of `path` triggers."""
        for component in components:
            lowered = component.lower()
            if lowered in METADATA_DIRECTORY_NAMES:
                return self._directory_reason(
                    path, component, "metadata", "holds tool or version-control state"
                )
            if lowered in VENDORED_DIRECTORY_NAMES:
                return self._directory_reason(
                    path, component, "vendored", "holds vendored third-party code"
                )
            if lowered in self._extra_directories:
                return self._directory_reason(
                    path, component, "vendored", "is an excluded directory"
                )
            if lowered in GENERATED_DIRECTORY_NAMES:
                return self._directory_reason(
                    path, component, "generated", "holds generated build output"
                )
            if lowered.endswith(GENERATED_DIRECTORY_SUFFIXES):
                return self._directory_reason(
                    path,
                    component,
                    "generated",
                    "is a generated packaging directory",
                )
        return None

    def _directory_reason(
        self, path: str, component: str, reason: ExclusionReason, detail: str
    ) -> FileExclusion:
        """Build the exclusion for a directory component that matched a rule."""
        return FileExclusion(
            path=path, reason=reason, detail=f"'{component}/' {detail}"
        )

    def _name_exclusion(self, path: str, name: str) -> FileExclusion | None:
        """Return the exclusion a file's own name triggers, or None."""
        lowered = name.lower()
        if lowered in GENERATED_FILE_NAMES:
            return FileExclusion(
                path=path,
                reason="generated",
                detail=f"'{name}' is a generated manifest or lock file",
            )
        if lowered.endswith(GENERATED_FILE_SUFFIXES) or (
            self._extra_suffixes and lowered.endswith(self._extra_suffixes)
        ):
            return FileExclusion(
                path=path,
                reason="generated",
                detail=f"'{name}' is compiled, minified, or code-generated",
            )
        return None


def _sized_paths(root: Path, paths: Iterable[str]) -> Iterator[tuple[str, int]]:
    """Yield each path with its size on disk, skipping what cannot be sized."""
    for path in paths:
        try:
            status = (root / path).stat()
        except OSError:
            continue
        yield path, status.st_size


def _path_components(path: str) -> tuple[str, ...]:
    """Return the meaningful components of a repository-relative path.

    Windows separators are treated as separators too, so a path written with
    backslashes cannot slip a vendored directory name past the filter.
    """
    normalized = PurePosixPath(path.replace("\\", "/"))
    return tuple(part for part in normalized.parts if part not in ("", "/", "."))

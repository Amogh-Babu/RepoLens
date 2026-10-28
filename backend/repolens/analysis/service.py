"""Analyze a repository tree with the registered `LanguageAnalyzer`s."""

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from repolens.analysis.models import (
    ParsedFile,
    ParseError,
    RepositoryAnalysis,
)
from repolens.analysis.ports import LanguageAnalyzer
from repolens.analysis.python_analyzer import PythonAnalyzer


# Directories that never hold reviewable source. Full exclusion rules (vendored
# code, generated files, size limits) are the ingestion filter's job; this is
# only enough to keep tree walks off build and metadata directories.
SKIPPED_DIRECTORY_NAMES = frozenset({".git", ".hg", ".svn", "__pycache__"})


class UnsupportedFileError(ValueError):
    """Raised when no registered analyzer handles a file."""

    def __init__(self, path: str) -> None:
        super().__init__(f"No registered LanguageAnalyzer supports {path!r}")
        self.path = path


class AnalysisService:
    """Turn source files into imports and top-level symbols per file.

    Analyzers are chosen by file path, so adding a language means registering
    another `LanguageAnalyzer` instead of changing this service. Files are read
    and parsed; they are never imported, executed, or evaluated.
    """

    def __init__(self, analyzers: Iterable[LanguageAnalyzer] | None = None) -> None:
        self._analyzers: tuple[LanguageAnalyzer, ...] = (
            tuple(analyzers) if analyzers is not None else (PythonAnalyzer(),)
        )

    @property
    def analyzers(self) -> tuple[LanguageAnalyzer, ...]:
        """Return the registered analyzers in match order."""
        return self._analyzers

    @property
    def languages(self) -> tuple[str, ...]:
        """Return the languages this service can analyze."""
        return tuple(analyzer.language for analyzer in self._analyzers)

    def analyzer_for(self, path: str) -> LanguageAnalyzer | None:
        """Return the first registered analyzer that supports `path`."""
        for analyzer in self._analyzers:
            if analyzer.supports(path):
                return analyzer
        return None

    def supports(self, path: str) -> bool:
        """Return whether any registered analyzer supports `path`."""
        return self.analyzer_for(path) is not None

    def analyze_source(self, path: str, source: str) -> ParsedFile:
        """Analyze in-memory `source` attributed to the repository path `path`."""
        analyzer = self.analyzer_for(path)
        if analyzer is None:
            raise UnsupportedFileError(path)
        return analyzer.analyze(path, source)

    def analyze_file(self, file_path: Path, repo_path: str | None = None) -> ParsedFile:
        """Analyze one file on disk, reported under `repo_path` if given.

        A file that cannot be decoded as UTF-8 or read at all is reported as an
        unparsed file rather than raising, so one unreadable file cannot fail
        the whole analysis.
        """
        path = repo_path if repo_path is not None else Path(file_path).as_posix()
        analyzer = self.analyzer_for(path)
        if analyzer is None:
            raise UnsupportedFileError(path)

        try:
            source = Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ParsedFile(
                path=path,
                language=analyzer.language,
                parsed=False,
                error=ParseError(message="File is not valid UTF-8 text"),
            )
        except OSError as error:
            return ParsedFile(
                path=path,
                language=analyzer.language,
                parsed=False,
                error=ParseError(message=f"File could not be read: {error.strerror}"),
            )

        return analyzer.analyze(path, source)

    def analyze_repository(self, root: str | Path) -> RepositoryAnalysis:
        """Analyze every supported file under `root`, keyed by relative path.

        Paths are POSIX-style and relative to `root`, matching the graph store
        and the frontend file explorer. Files no analyzer supports are listed in
        `skipped_paths`. Results are sorted by path so analyses are repeatable.

        Raises NotADirectoryError if `root` is not an existing directory, so a
        bad checkout path cannot look like an empty repository.
        """
        root_path = Path(root)
        if not root_path.is_dir():
            raise NotADirectoryError(f"Not a repository directory: {root_path}")
        analyzed: list[ParsedFile] = []
        skipped: list[str] = []

        for file_path, repo_path in _walk_files(root_path):
            if self.supports(repo_path):
                analyzed.append(self.analyze_file(file_path, repo_path))
            else:
                skipped.append(repo_path)

        analyzed.sort(key=lambda parsed: parsed.path)
        skipped.sort()
        return RepositoryAnalysis(
            root=root_path.as_posix(),
            files=tuple(analyzed),
            skipped_paths=tuple(skipped),
        )


def _walk_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield each regular file under `root` as (full path, relative POSIX path).

    Symlinks are not followed, so an analysis cannot escape the directory it
    was given or loop on a cyclic link.
    """
    for directory, subdirectories, file_names in os.walk(root):
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in SKIPPED_DIRECTORY_NAMES
        )
        for file_name in sorted(file_names):
            file_path = Path(directory) / file_name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            yield file_path, file_path.relative_to(root).as_posix()

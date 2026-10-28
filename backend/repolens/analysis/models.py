"""Data models for per-file source analysis (`repolens.analysis`).

These records are language-neutral: a `LanguageAnalyzer` for another language
maps its own syntax onto the same `ParsedImport` and `ParsedSymbol` shapes.
Imports are reported exactly as written; resolving them to files in the
repository and classifying them as internal or external happens later in the
pipeline (see `repolens.analysis.adapter`).
"""

from dataclasses import dataclass
from typing import Literal

from repolens.graph.models import SymbolKind


ImportForm = Literal["import", "from"]


@dataclass(frozen=True)
class ParsedSymbol:
    """A top-level symbol declared by a source file."""

    name: str
    kind: SymbolKind
    line: int


@dataclass(frozen=True)
class ParsedImport:
    """A module reference extracted from a source file's import statements.

    `module` is the dotted module path without leading dots, and `level` is the
    relative-import depth (0 for an absolute import). `symbols` holds the names
    taken from the module by a `from` import, including `'*'` for a star
    import. Several statements that reference the same module are merged into
    one record, so one import maps to at most one dependency edge.
    """

    module: str | None
    form: ImportForm = "import"
    level: int = 0
    symbols: tuple[str, ...] = ()
    line: int = 1

    @property
    def raw_name(self) -> str:
        """Return the module reference as written, e.g. 'os.path' or '.service'."""
        return "." * self.level + (self.module or "")

    @property
    def is_relative(self) -> bool:
        """Return whether this is a relative (dotted) import."""
        return self.level > 0


@dataclass(frozen=True)
class ParseError:
    """Why a source file could not be parsed."""

    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class ParsedFile:
    """Imports and top-level symbols extracted from a single source file.

    An unparsable file is still reported, with `parsed=False`, an `error`, and
    empty imports and symbols, so that one bad file never hides the rest of a
    repository.
    """

    path: str
    language: str
    parsed: bool = True
    line_count: int = 0
    imports: tuple[ParsedImport, ...] = ()
    symbols: tuple[ParsedSymbol, ...] = ()
    error: ParseError | None = None


@dataclass(frozen=True)
class RepositoryAnalysis:
    """Every analyzed file in one repository tree, in sorted path order."""

    root: str
    files: tuple[ParsedFile, ...] = ()
    skipped_paths: tuple[str, ...] = ()

    @property
    def parsed_count(self) -> int:
        """Return the number of files that parsed successfully."""
        return sum(1 for file in self.files if file.parsed)

    @property
    def unparsed_count(self) -> int:
        """Return the number of files that failed to parse."""
        return sum(1 for file in self.files if not file.parsed)

    def get(self, path: str) -> ParsedFile | None:
        """Return the analyzed file at `path`, or None if it was not analyzed."""
        for file in self.files:
            if file.path == path:
                return file
        return None

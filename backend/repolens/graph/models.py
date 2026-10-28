"""Data models for the RepoLens dependency graph store."""

from dataclasses import dataclass
from typing import Literal


SymbolKind = Literal["function", "class", "variable"]
ImportKind = Literal["internal", "external", "unresolved"]
AnalysisStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
AnalysisStage = Literal[
    "resolving",
    "downloading",
    "filtering",
    "parsing",
    "classifying",
    "storing",
]


@dataclass(frozen=True)
class SymbolRecord:
    """A symbol extracted from a source file."""

    name: str
    kind: SymbolKind
    line: int


@dataclass(frozen=True)
class ImportRecord:
    """An import extracted and classified from a source file.

    `raw_name` is the reference as written, so it collapses the names taken by
    a `from` import: `from . import config` renders as `"."` and
    `from app.services import billing` as `"app.services"`. `level` and
    `symbols` keep the relative-import depth and those imported names, which
    is what lets the classifier resolve `config` to `app/config.py` and
    `billing` to either `app/services/billing.py` or a name re-exported by
    `app/services/__init__.py`. Only `kind`, `target_path`, and
    `target_package` are persisted; the classifier fills them in before the
    storing stage.
    """

    raw_name: str
    kind: ImportKind
    target_path: str | None = None
    target_package: str | None = None
    level: int = 0
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommentRecord:
    """A comment extracted from a source file."""

    line: int
    text: str


@dataclass(frozen=True)
class AnalyzedFile:
    """All extracted data for a single file in an analyzed repository."""

    path: str
    module: str = ""
    parsed: bool = True
    line_count: int = 0
    symbols: tuple[SymbolRecord, ...] = ()
    imports: tuple[ImportRecord, ...] = ()
    comments: tuple[CommentRecord, ...] = ()


@dataclass(frozen=True)
class AnalysisCounts:
    """Summary counts for a repository analysis."""

    analyzed: int = 0
    excluded: int = 0
    unparsed: int = 0


@dataclass(frozen=True)
class AnalysisErrorRecord:
    """Structured error information stored when an analysis fails."""

    code: str
    message: str
    hint: str | None = None


@dataclass(frozen=True)
class AnalysisRecord:
    """Complete analysis payload to persist in the graph store."""

    analysis_id: str
    repo: str
    sha: str
    ref: str | None = None
    status: AnalysisStatus = "completed"
    stage: AnalysisStage | None = None
    from_cache: bool = False
    created_at: float = 0.0
    expires_at: float = 0.0
    counts: AnalysisCounts = AnalysisCounts()
    error: AnalysisErrorRecord | None = None
    files: tuple[AnalyzedFile, ...] = ()


@dataclass(frozen=True)
class ModuleGroup:
    """A group of files sharing a module directory for the dependency map."""

    id: str
    name: str
    file_paths: tuple[str, ...]

    @property
    def module(self) -> str:
        return self.id

    @property
    def files(self) -> tuple[str, ...]:
        return self.file_paths


@dataclass(frozen=True)
class GraphNode:
    """A file node in the dependency map."""

    path: str
    module: str
    parsed: bool
    line_count: int


@dataclass(frozen=True)
class GraphEdge:
    """A directed internal import edge from source file to target file."""

    source: str
    target: str
    raw_name: str = ""


@dataclass(frozen=True)
class DependencyGraph:
    """Graph payload returned by GET /analyses/{id}/graph."""

    analysis_id: str
    repo: str
    sha: str
    modules: tuple[ModuleGroup, ...]
    files: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @property
    def nodes(self) -> tuple[GraphNode, ...]:
        return self.files


@dataclass(frozen=True)
class SymbolDetail:
    """Symbol metadata and source link for the file detail panel."""

    name: str
    kind: SymbolKind
    line: int
    source_url: str


@dataclass(frozen=True)
class InternalImportDetail:
    """An internal import resolved to another file in the repository."""

    raw_name: str
    target_path: str


@dataclass(frozen=True)
class ExternalImportDetail:
    """An external stdlib or third-party import."""

    raw_name: str
    package: str


@dataclass(frozen=True)
class FileDetail:
    """File detail payload returned by GET /analyses/{id}/files/{path}."""

    analysis_id: str
    repo: str
    sha: str
    path: str
    module: str
    parsed: bool
    line_count: int
    source_url: str
    symbols: tuple[SymbolDetail, ...]
    imports: tuple[ImportRecord, ...]
    internal_imports: tuple[InternalImportDetail, ...]
    external_imports: tuple[ExternalImportDetail, ...]
    unresolved_imports: tuple[str, ...]
    imported_by: tuple[str, ...]

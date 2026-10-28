"""Map analysis results onto the graph store's records.

Keeping the mapping here lets `repolens.analysis` stay language-neutral and
storage-agnostic: analyzers report what a file declares, and this adapter
describes it in the shape `repolens.graph` persists.
"""

from repolens.analysis.models import ParsedFile, RepositoryAnalysis
from repolens.graph.models import (
    AnalysisCounts,
    AnalyzedFile,
    ImportRecord,
    SymbolRecord,
)


def to_analyzed_file(parsed: ParsedFile) -> AnalyzedFile:
    """Convert one `ParsedFile` into a storable `AnalyzedFile`.

    Imports keep the name written in the source and are reported as
    `unresolved`: deciding whether a name points at another file in the
    repository or at an external package needs the whole file list, so the
    import classifier assigns the final `internal` or `external` kind and the
    target path. `module` is left empty for the store to infer from the path.
    """
    return AnalyzedFile(
        path=parsed.path,
        parsed=parsed.parsed,
        line_count=parsed.line_count,
        symbols=tuple(
            SymbolRecord(name=symbol.name, kind=symbol.kind, line=symbol.line)
            for symbol in parsed.symbols
        ),
        imports=tuple(
            ImportRecord(raw_name=imported.raw_name, kind="unresolved")
            for imported in parsed.imports
        ),
    )


def to_analyzed_files(analysis: RepositoryAnalysis) -> tuple[AnalyzedFile, ...]:
    """Convert every analyzed file in a repository analysis."""
    return tuple(to_analyzed_file(parsed) for parsed in analysis.files)


def to_analysis_counts(analysis: RepositoryAnalysis) -> AnalysisCounts:
    """Summarize a repository analysis for the analysis status endpoint."""
    return AnalysisCounts(
        analyzed=len(analysis.files),
        excluded=len(analysis.skipped_paths),
        unparsed=analysis.unparsed_count,
    )

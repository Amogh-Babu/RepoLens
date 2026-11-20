"""Protocol definition for the RepoLens graph store."""

from collections.abc import Iterable
from typing import Protocol

from repolens.graph.models import (
    AnalysisRecord,
    AnalyzedFile,
    DependencyGraph,
    FileDetail,
    FileEmbeddingRecord,
    SemanticIndex,
)
from repolens.search.models import SearchDocument


class GraphStore(Protocol):
    """Persist and query repository analysis graphs."""

    def save(self, analysis: AnalysisRecord) -> None:
        """Persist a complete repository analysis atomically."""

    def build_embeddings(
        self, files: tuple[AnalyzedFile, ...]
    ) -> tuple[FileEmbeddingRecord, ...]:
        """Create bounded search vectors for parsed files."""

    def build_semantic_index(
        self, files: tuple[AnalyzedFile, ...]
    ) -> SemanticIndex:
        """Create search vectors within the chunk budget, with their status."""

    def get_graph(self, analysis_id: str) -> DependencyGraph:
        """Return module groups, file nodes, and internal import edges."""

    def get_file(self, analysis_id: str, path: str) -> FileDetail:
        """Return detail panel data for one file in an analysis."""

    def get_search_documents(self, analysis_id: str) -> Iterable[SearchDocument]:
        """Return searchable documents for SearchService."""

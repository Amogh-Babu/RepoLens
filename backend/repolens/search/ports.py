from collections.abc import Iterable
from typing import Protocol

from repolens.search.models import SearchDocument
from repolens.search.embedding import ChunkVectors, Embedding


class AnalysisUnavailableError(LookupError):
    """Raised when an analysis is missing or has expired from the search index."""


class SearchIndex(Protocol):
    """Read normalized searchable records for one analyzed repository."""

    def get_search_documents(self, analysis_id: str) -> Iterable[SearchDocument]:
        """Return records belonging only to the requested analysis."""
        ...

    def get_search_embeddings(
        self, analysis_id: str
    ) -> ChunkVectors | dict[str, list[tuple[str, Embedding]]]:
        """Return the stored chunk vectors of an analysis.

        `ChunkVectors` is what the graph store returns; a mapping of
        `{path: [(chunk text, vector), ...]}` is accepted too.
        """
        ...
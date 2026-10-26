from collections.abc import Iterable
from typing import Protocol

from repolens.search.models import SearchDocument


class AnalysisUnavailableError(LookupError):
    """Raised when an analysis is missing or has expired from the search index."""


class SearchIndex(Protocol):
    """Read normalized searchable records for one analyzed repository."""

    def get_search_documents(self, analysis_id: str) -> Iterable[SearchDocument]:
        """Return records belonging only to the requested analysis."""
        ...
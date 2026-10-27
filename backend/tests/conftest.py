"""Shared pytest fixtures for backend tests.

pytest loads this file automatically; any test in this directory can request a
fixture by naming it as a parameter.
"""

from collections.abc import Callable

import pytest

from repolens.search import SearchDocument, SearchService


class InMemorySearchIndex:
    """A `SearchIndex` backed by a dict, so tests need no graph store."""

    def __init__(self, documents_by_analysis: dict[str, list[SearchDocument]]) -> None:
        self._documents_by_analysis = documents_by_analysis

    def get_search_documents(self, analysis_id: str) -> list[SearchDocument]:
        return self._documents_by_analysis.get(analysis_id, [])


@pytest.fixture
def make_search_service() -> Callable[..., SearchService]:
    """Build a `SearchService` whose only analysis, "analysis-1", holds `documents`."""

    def build(*documents: SearchDocument) -> SearchService:
        return SearchService(InMemorySearchIndex({"analysis-1": list(documents)}))

    return build

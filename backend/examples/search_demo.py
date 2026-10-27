import json
from pathlib import Path

from fastapi import FastAPI

from repolens.api.search import install_search_api
from repolens.search import AnalysisUnavailableError, SearchDocument, SearchService


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_mini_repo"
)


class MiniRepoSearchIndex:
    """Expose the mini repository's hand-annotated records to the search API."""

    def __init__(self) -> None:
        data = json.loads(
            (_FIXTURE_ROOT / "search_index.json").read_text(encoding="utf-8")
        )
        self.analysis_id: str = data["analysis_id"]
        self._documents = tuple(
            SearchDocument(
                path=record["path"],
                symbols=tuple(record["symbols"]),
                references=tuple(record["references"]),
                comments=tuple(record["comments"]),
                depended_on_by=tuple(record["depended_on_by"]),
            )
            for record in data["documents"]
        )

    def get_search_documents(self, analysis_id: str) -> tuple[SearchDocument, ...]:
        if analysis_id != self.analysis_id:
            raise AnalysisUnavailableError(analysis_id)
        return self._documents


_index = MiniRepoSearchIndex()
app = FastAPI(title="RepoLens Search Demo")
install_search_api(app, SearchService(_index))
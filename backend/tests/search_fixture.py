import json
from pathlib import Path

from repolens.search import AnalysisUnavailableError, SearchDocument


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "search_mini_repo"


class MiniRepoSearchIndex:
    """Serve the hand-annotated records for the search mini repository."""

    def __init__(self) -> None:
        index_path = FIXTURE_ROOT / "search_index.json"
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.analysis_id: str = data["analysis_id"]
        self.documents = tuple(
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
        return self.documents
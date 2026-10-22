import re
from collections.abc import Iterable

from repolens.search.models import (
    MatchEvidence,
    RankedFile,
    SearchDocument,
    SearchPage,
)
from repolens.search.ports import SearchIndex


_MAX_QUERY_LENGTH = 200
_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100
_MAX_EVIDENCE_LENGTH = 80
_FIELD_WEIGHTS = {
    "filename": 8.0,
    "symbol": 6.0,
    "reference": 4.0,
    "comment": 2.0,
}
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


class QueryValidationError(ValueError):
    """Raised when a search query does not meet the API contract."""


class PaginationValidationError(ValueError):
    """Raised when a search page's offset or size is invalid."""


class SearchService:
    """Search analyzed repository records and suggest a reading order."""

    def __init__(self, index: SearchIndex) -> None:
        self._index = index

    def search(
        self,
        analysis_id: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = _DEFAULT_PAGE_SIZE,
    ) -> SearchPage:
        terms = self._parse_query(query)
        self._validate_pagination(offset, limit)
        documents = self._index.get_search_documents(analysis_id)
        candidates: list[tuple[SearchDocument, tuple[MatchEvidence, ...], float]] = []

        for document in documents:
            matches = self._match_document(document, terms)
            if not matches:
                continue

            matched_terms = {term for match in matches for term in match.matched_terms}
            score = sum(
                _FIELD_WEIGHTS[match.kind] * len(match.matched_terms)
                for match in matches
            )
            score += len(matched_terms) * 3.0
            candidates.append((document, matches, score))

        candidate_paths = {document.path for document, _, _ in candidates}
        ranked: list[RankedFile] = []
        for document, matches, score in candidates:
            dependency_count = len(candidate_paths.intersection(document.depended_on_by))
            score += dependency_count * 1.5
            ranked.append(
                RankedFile(
                    path=document.path,
                    score=score,
                    reason=self._build_reason(matches, dependency_count),
                    matches=matches,
                )
            )

        ordered = sorted(ranked, key=lambda result: (-result.score, result.path.casefold()))
        page_results = tuple(ordered[offset : offset + limit])
        return SearchPage(
            results=page_results,
            total=len(ordered),
            offset=offset,
            limit=limit,
            has_more=offset + len(page_results) < len(ordered),
        )

    @staticmethod
    def _validate_pagination(offset: int, limit: int) -> None:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise PaginationValidationError("Offset must be a non-negative integer.")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _MAX_PAGE_SIZE
        ):
            raise PaginationValidationError(
                f"Limit must be an integer between 1 and {_MAX_PAGE_SIZE}."
            )

    @staticmethod
    def _parse_query(query: str) -> tuple[str, ...]:
        if not isinstance(query, str):
            raise QueryValidationError("Query must be a string.")
        if len(query) > _MAX_QUERY_LENGTH:
            raise QueryValidationError("Query must be 200 characters or fewer.")
        terms = tuple(dict.fromkeys(term.casefold() for term in _TOKEN_PATTERN.findall(query)))
        if not terms:
            raise QueryValidationError("Enter a keyword to search.")
        return terms

    @staticmethod
    def _match_document(
        document: SearchDocument, terms: tuple[str, ...]
    ) -> tuple[MatchEvidence, ...]:
        fields: tuple[tuple[str, Iterable[str]], ...] = (
            ("filename", (document.path,)),
            ("symbol", document.symbols),
            ("reference", document.references),
            ("comment", document.comments),
        )
        matches: list[MatchEvidence] = []
        for kind, values in fields:
            for value in values:
                normalized_value = value.casefold()
                matched_terms = tuple(term for term in terms if term in normalized_value)
                if matched_terms:
                    matches.append(MatchEvidence(kind, value, matched_terms))
        return tuple(matches)

    @staticmethod
    def _build_reason(matches: tuple[MatchEvidence, ...], dependency_count: int) -> str:
        evidence = [
            f"{match.kind} '{SearchService._one_line(match.value)}'"
            for match in matches[:2]
        ]
        reason = f"Matches {', '.join(evidence)}"
        if len(matches) > 2:
            reason += f" and {len(matches) - 2} more match(es)"
        if dependency_count:
            reason += f"; depended on by {dependency_count} other matching file(s)"
        return reason + "."

    @staticmethod
    def _one_line(value: str) -> str:
        flattened = " ".join(value.split())
        if len(flattened) <= _MAX_EVIDENCE_LENGTH:
            return flattened
        return flattened[: _MAX_EVIDENCE_LENGTH - 3] + "..."
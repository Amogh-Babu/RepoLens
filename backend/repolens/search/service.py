import heapq
import logging
import re
from collections.abc import Iterable
from dataclasses import replace

from repolens.search.embedding import (
    Embedder,
    HashEmbedder,
    cosine_similarity,
)
from repolens.search.models import (
    MatchEvidence,
    MatchKind,
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
    "member": 5.0,
    "reference": 4.0,
    "docstring": 3.0,
    "comment": 2.0,
}
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)
_LOGGER = logging.getLogger(__name__)
_RRF_K = 60
_KEYWORD_RRF_WEIGHT = 8
_SEMANTIC_RRF_WEIGHT = 1
_SEMANTIC_RESULT_LIMIT = 100

# Docstrings and comments are sentences, so a short term would match inside
# almost every one of them ("i" in "this", "in" in "using"). In these fields a
# term must start a word, and words that carry no topic are not matched at all.
_PROSE_KINDS = frozenset({"docstring", "comment"})
_PROSE_STOP_WORDS = frozenset(
    """
    a about all also am an and any are as at be been but by can could do does
    for from get had has have how i if im in into is it its just me my need no
    not of on or our should so some than that the their them then there these
    they this to too us use used using want was we were what when where which
    who why will with would you your
    """.split()
)


class QueryValidationError(ValueError):
    """Raised when a search query does not meet the API contract."""


class PaginationValidationError(ValueError):
    """Raised when a search page's offset or size is invalid."""


class SearchService:
    """Search analyzed repository records and suggest a reading order."""

    def __init__(self, index: SearchIndex, embedder: Embedder | None = None) -> None:
        self._index = index
        self._embedder = embedder or getattr(index, "embedder", None) or HashEmbedder()

    def search(
        self,
        analysis_id: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = _DEFAULT_PAGE_SIZE,
        include_semantic: bool = True,
    ) -> SearchPage:
        terms = self._topic_terms(self._parse_query(query))
        self._validate_pagination(offset, limit)
        documents = list(self._index.get_search_documents(analysis_id))
        documents_by_path = {document.path: document for document in documents}
        keyword_matches: dict[str, tuple[MatchEvidence, ...]] = {}
        keyword_scores: dict[str, float] = {}

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
            keyword_matches[document.path] = matches
            keyword_scores[document.path] = score

        semantic_scores = (
            self._semantic_scores(analysis_id, query, documents)
            if include_semantic
            else {}
        )
        keyword_paths = set(keyword_scores)
        keyword_order = sorted(
            keyword_scores,
            key=lambda path: (
                -(
                    keyword_scores[path]
                    + len(
                        keyword_paths.intersection(
                            documents_by_path[path].depended_on_by
                        )
                    )
                    * 1.5
                ),
                path.casefold(),
            ),
        )
        semantic_order = sorted(
            semantic_scores,
            key=lambda path: (-semantic_scores[path][0], path.casefold()),
        )[:_SEMANTIC_RESULT_LIMIT]
        keyword_ranks = {path: rank for rank, path in enumerate(keyword_order, 1)}
        semantic_ranks = {path: rank for rank, path in enumerate(semantic_order, 1)}
        candidate_paths = set(keyword_ranks) | set(semantic_ranks)
        candidates: list[tuple[SearchDocument, tuple[MatchEvidence, ...], float]] = []
        ranked: list[RankedFile] = []
        for path in candidate_paths:
            document = documents_by_path[path]
            matches = keyword_matches.get(path, ())
            if not matches:
                matches = (
                    MatchEvidence(
                        "semantic",
                        semantic_scores[path][1][:_MAX_EVIDENCE_LENGTH],
                        (),
                    ),
                )
            dependency_count = len(candidate_paths.intersection(document.depended_on_by))
            keyword_rank = keyword_ranks.get(path)
            semantic_rank = semantic_ranks.get(path)
            if keyword_rank is not None and semantic_rank is not None:
                score = _KEYWORD_RRF_WEIGHT / (_RRF_K + keyword_rank)
                score += _SEMANTIC_RRF_WEIGHT / (_RRF_K + semantic_rank)
                score += dependency_count * 0.0001
            elif keyword_rank is not None:
                score = keyword_scores[path] + dependency_count * 1.5
            else:
                score = _SEMANTIC_RRF_WEIGHT / (_RRF_K + (semantic_rank or 0))
            candidates.append((document, matches, score))
            ranked.append(
                RankedFile(
                    path=document.path,
                    score=score,
                    reason=self._build_reason(matches, dependency_count),
                    matches=matches,
                )
            )

        keyword_candidates = [
            candidate for candidate in candidates if candidate[0].path in keyword_ranks
        ]
        semantic_candidates = [
            candidate for candidate in candidates if candidate[0].path not in keyword_ranks
        ]
        keyword_ranked = [
            result for result in ranked if result.path in keyword_ranks
        ]
        semantic_ranked = [
            result for result in ranked if result.path not in keyword_ranks
        ]
        ordered = self._reading_order(keyword_ranked, keyword_candidates)
        if semantic_ranked:
            ordered.extend(self._reading_order(semantic_ranked, semantic_candidates))
        page_results = tuple(ordered[offset : offset + limit])
        return SearchPage(
            results=page_results,
            total=len(ordered),
            offset=offset,
            limit=limit,
            has_more=offset + len(page_results) < len(ordered),
        )

    def _semantic_scores(
        self,
        analysis_id: str,
        query: str,
        documents: list[SearchDocument],
    ) -> dict[str, tuple[float, str]]:
        get_embeddings = getattr(self._index, "get_search_embeddings", None)
        if get_embeddings is None:
            return {}
        try:
            embeddings = get_embeddings(analysis_id)
            query_vector = self._embedder.embed([f"query: {query}"])[0]
        except Exception:
            _LOGGER.warning(
                "Semantic search unavailable for analysis %s", analysis_id, exc_info=True
            )
            return {}
        scores: dict[str, tuple[float, str]] = {}
        for document in documents:
            chunks = embeddings.get(document.path)
            if not chunks:
                continue
            best_score, best_text = max(
                (
                    (cosine_similarity(query_vector, vector), text)
                    for text, vector in chunks
                ),
                key=lambda item: item[0],
            )
            if best_score > 0:
                scores[document.path] = (best_score, best_text)
        return scores

    @staticmethod
    def _reading_order(
        ranked: list[RankedFile],
        candidates: list[tuple[SearchDocument, tuple[MatchEvidence, ...], float]],
    ) -> list[RankedFile]:
        """Order results dependencies first, and say why each file is placed.

        A Kahn topological sort over the imports between matching files:
        a file is ready once every matching file it imports has been placed,
        and among ready files the stronger match goes first. When only
        import cycles remain, the strongest remaining match is placed next.
        """
        results_by_path = {result.path: result for result in ranked}
        dependents: dict[str, set[str]] = {path: set() for path in results_by_path}
        prerequisites: dict[str, set[str]] = {path: set() for path in results_by_path}

        for document, _, _ in candidates:
            dependency_path = document.path
            for dependent_path in document.depended_on_by:
                if dependent_path not in results_by_path:
                    continue
                if dependent_path == dependency_path:
                    continue
                dependents[dependency_path].add(dependent_path)
                prerequisites[dependent_path].add(dependency_path)

        prerequisite_count = {path: len(deps) for path, deps in prerequisites.items()}
        ready: list[tuple[float, str, str]] = []
        for path, count in prerequisite_count.items():
            if count == 0:
                result = results_by_path[path]
                heapq.heappush(ready, (-result.score, path.casefold(), path))

        ordered_paths: list[str] = []
        placed: set[str] = set()
        cycle_partners: dict[str, tuple[list[str], list[str]]] = {}
        while len(ordered_paths) < len(ranked):
            if not ready:
                remaining_paths = set(results_by_path).difference(placed)
                cycle_break = min(
                    remaining_paths,
                    key=lambda path: (-results_by_path[path].score, path.casefold()),
                )
                cycle_partners[cycle_break] = SearchService._cycle_partners(
                    cycle_break, prerequisites, placed
                )
                result = results_by_path[cycle_break]
                heapq.heappush(ready, (-result.score, cycle_break.casefold(), cycle_break))

            _, _, path = heapq.heappop(ready)
            if path in placed:
                continue
            ordered_paths.append(path)
            placed.add(path)
            for dependent_path in dependents[path]:
                if dependent_path in placed:
                    continue
                prerequisite_count[dependent_path] -= 1
                if prerequisite_count[dependent_path] == 0:
                    result = results_by_path[dependent_path]
                    heapq.heappush(
                        ready,
                        (-result.score, dependent_path.casefold(), dependent_path),
                    )

        position = {path: index for index, path in enumerate(ordered_paths)}
        ordered: list[RankedFile] = []
        for path in ordered_paths:
            before = sorted(
                (dep for dep in prerequisites[path] if position[dep] < position[path]),
                key=lambda dep: position[dep],
            )
            after = sorted(
                (dep for dep in dependents[path] if position[dep] > position[path]),
                key=lambda dep: position[dep],
            )
            in_cycle, held_back = cycle_partners.get(path, ([], []))
            reason = SearchService._build_order_reason(before, after, in_cycle, held_back)
            ordered.append(replace(results_by_path[path], order_reason=reason))
        return ordered

    @staticmethod
    def _cycle_partners(
        path: str, prerequisites: dict[str, set[str]], placed: set[str]
    ) -> tuple[list[str], list[str]]:
        """Split the unplaced files `path` imports by why they could not go first.

        The first list imports `path` back, directly or through other
        unplaced files, so they share an import cycle with it. The second
        list waits on some other cycle.
        """
        in_cycle: list[str] = []
        held_back: list[str] = []
        for dependency in sorted(prerequisites[path].difference(placed), key=str.casefold):
            seen: set[str] = set()
            stack = [dependency]
            loops_back = False
            while stack and not loops_back:
                current = stack.pop()
                for upstream in prerequisites[current]:
                    if upstream == path:
                        loops_back = True
                        break
                    if upstream not in placed and upstream not in seen:
                        seen.add(upstream)
                        stack.append(upstream)
            (in_cycle if loops_back else held_back).append(dependency)
        return in_cycle, held_back

    @staticmethod
    def _build_order_reason(
        imports_before: list[str],
        imported_by_after: list[str],
        cycle_with: list[str],
        held_back: list[str],
    ) -> str:
        """Explain a file's place in the reading order in one sentence.

        `imports_before` are matching files it imports that come earlier and
        `imported_by_after` are matching files that import it and come later.
        `cycle_with` and `held_back` are files it imports that still come
        later: the first share an import cycle with it, and the second are
        held back by a cycle elsewhere.
        """
        parts: list[str] = []
        if cycle_with:
            parts.append(
                f"Part of an import cycle with {SearchService._name_files(cycle_with)}, "
                "so it is placed by how strongly it matches"
            )
        if held_back:
            verb = "is" if len(held_back) == 1 else "are"
            parts.append(
                f"Comes before {SearchService._name_files(held_back)}, which it imports, "
                f"because {'that file' if len(held_back) == 1 else 'they'} {verb} "
                "held back by an import cycle"
            )
        if imports_before:
            parts.append(
                f"Comes after {SearchService._name_files(imports_before)}, "
                f"which it imports"
            )
        if imported_by_after:
            verb = "imports" if len(imported_by_after) == 1 else "import"
            parts.append(
                f"Comes before {SearchService._name_files(imported_by_after)}, "
                f"which {verb} it"
            )
        if not parts:
            return (
                "Does not import or get imported by the other results, "
                "so it is placed by how strongly it matches."
            )
        sentence = "; ".join(parts[:1] + [part[0].lower() + part[1:] for part in parts[1:]])
        return sentence + "."

    @staticmethod
    def _name_files(paths: list[str]) -> str:
        """Name up to two files, then count the rest."""
        if len(paths) == 1:
            return paths[0]
        if len(paths) == 2:
            return f"{paths[0]} and {paths[1]}"
        return f"{paths[0]}, {paths[1]} and {len(paths) - 2} more"

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
    def _topic_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
        """Drop the words of a question that carry no topic.

        "where do I check if a signature expired" should search for
        `check`, `signature`, and `expired`: as substrings, `i`, `a`, and `do`
        are inside nearly every path and name. A query made only of such
        words is searched as written, so `io` or `do` still finds something.
        """
        topical = tuple(
            term for term in terms if len(term) > 1 and term not in _PROSE_STOP_WORDS
        )
        return topical or terms

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
        fields: tuple[tuple[MatchKind, Iterable[str]], ...] = (
            ("filename", (document.path,)),
            ("symbol", document.symbols),
            ("member", document.members),
            ("reference", document.references),
            ("docstring", document.docstrings),
            ("comment", document.comments),
        )
        prose_patterns = {
            term: re.compile(rf"(?<![^\W_]){re.escape(term)}")
            for term in terms
            if len(term) > 1 and term not in _PROSE_STOP_WORDS
        }
        matches: list[MatchEvidence] = []
        for kind, values in fields:
            for value in values:
                normalized_value = value.casefold()
                if kind in _PROSE_KINDS:
                    matched_terms = tuple(
                        term
                        for term, pattern in prose_patterns.items()
                        if pattern.search(normalized_value)
                    )
                else:
                    matched_terms = tuple(
                        term for term in terms if term in normalized_value
                    )
                if matched_terms:
                    matches.append(MatchEvidence(kind, value, matched_terms))
        return tuple(matches)

    @staticmethod
    def _build_reason(matches: tuple[MatchEvidence, ...], dependency_count: int) -> str:
        if matches and matches[0].kind == "semantic":
            reason = (
                "Semantically related prose or symbols: "
                f"'{SearchService._one_line(matches[0].value)}'"
            )
            return reason + "."
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
"""Build the bounded context for an AI overview of one search.

The overview explains the reading list the user is looking at, so the
context starts from the same `SearchService.search` call with the same query
and reading goal: the top results, in the same order, with the same "why it
matches" and "why this position" reasons. Each result adds what the analysis
already stores about the file (symbol names, its first docstring line, which
other results it imports) and, when one is cached, its verified AI file
summary. Nothing is downloaded and no source code is sent.
"""

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
import re

from repolens.ai.search_models import (
    OVERVIEW_RESULT_LIMIT,
    SearchContextFile,
    SearchOverviewContext,
)
from repolens.onboarding.service import first_docstring_line
from repolens.search import SearchService
from repolens.search.models import SearchDocument
from repolens.search.service import SearchIntent


_MAX_SYMBOLS = 15
_WHITESPACE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Return the cache key form of a query: trimmed, casefolded, one space."""
    return _WHITESPACE.sub(" ", query).strip().casefold()


def build_search_context(
    search_service: SearchService,
    documents: list[SearchDocument],
    cached_summaries: Mapping[str, str],
    analysis_id: str,
    query: str,
    intent: SearchIntent | None,
    *,
    max_input_chars: int,
    limit: int = OVERVIEW_RESULT_LIMIT,
) -> SearchOverviewContext:
    """Return the overview context for one search, bounded to `max_input_chars`.

    Args:
      search_service: The service that produced the user's reading list.
      documents: The analysis's search documents (symbols, docstrings, imports).
      cached_summaries: `{path: summary}` of verified AI file summaries
        already cached for this analysis. Read only, never generated.
      analysis_id: The analysis searched.
      query: The query as the user typed it.
      intent: The reading goal, or None for the topic overall.
      max_input_chars: Budget for the serialized context.
      limit: How many top results to include.

    Raises:
      QueryValidationError: The query is empty or too long.
      AnalysisUnavailableError / GraphStoreError: The analysis is unavailable.
    """
    page = search_service.search(analysis_id, query, limit=limit, intent=intent)
    by_path = {document.path: document for document in documents}
    top_paths = [result.path for result in page.results]

    files = []
    for position, result in enumerate(page.results, start=1):
        document = by_path.get(result.path, SearchDocument(path=result.path))
        imports_within = tuple(
            sorted(
                other
                for other in top_paths
                if other != result.path
                and result.path in by_path.get(other, SearchDocument(path=other)).depended_on_by
            )
        )
        files.append(
            SearchContextFile(
                path=result.path,
                position=position,
                reason=result.reason,
                order_reason=result.order_reason,
                symbols=(*document.symbols, *document.members)[:_MAX_SYMBOLS],
                docstring=first_docstring_line(document),
                imports_within=imports_within,
                ai_summary=cached_summaries.get(result.path) or None,
            )
        )

    context = SearchOverviewContext(
        query=query.strip(),
        query_norm=normalize_query(query),
        intent=intent,
        files=tuple(files),
        results_hash=hashlib.sha256("\n".join(top_paths).encode("utf-8")).hexdigest(),
        total_results=page.total,
    )
    return _fit(context, max_input_chars)


def context_payload(context: SearchOverviewContext) -> dict[str, object]:
    """Return the untrusted data sent to the model for one overview."""
    return {
        "query": context.query,
        "readingGoal": context.intent or "the topic overall",
        "totalMatchingFiles": context.total_results,
        "results": [
            {
                "position": item.position,
                "path": item.path,
                "whyItMatches": item.reason,
                "whyThisPosition": item.order_reason,
                "symbols": list(item.symbols),
                "docstring": item.docstring,
                "importsOtherResults": list(item.imports_within),
                **({"verifiedAiSummary": item.ai_summary} if item.ai_summary else {}),
            }
            for item in context.files
        ],
    }


def _size(context: SearchOverviewContext) -> int:
    return len(json.dumps(context_payload(context), ensure_ascii=True))


def _fit(context: SearchOverviewContext, max_input_chars: int) -> SearchOverviewContext:
    """Shrink the context until it fits: summaries, then symbols, then files.

    The `results_hash` is kept: it identifies the search, not how much of it
    fitted.
    """
    if _size(context) <= max_input_chars:
        return context
    # Later results' cached summaries go first, then everyone's symbol lists
    # shrink, then the lowest-ranked results drop out (the first always stays).
    files = list(context.files)
    for index in reversed(range(len(files))):
        if files[index].ai_summary:
            files[index] = replace(files[index], ai_summary=None)
            if _size(replace(context, files=tuple(files))) <= max_input_chars:
                return replace(context, files=tuple(files))
    for keep in (8, 4, 0):
        files = [replace(item, symbols=item.symbols[:keep]) for item in files]
        if _size(replace(context, files=tuple(files))) <= max_input_chars:
            return replace(context, files=tuple(files))
    while len(files) > 1 and _size(replace(context, files=tuple(files))) > max_input_chars:
        files.pop()
    return replace(context, files=tuple(files))

"""Data models for AI search overviews.

`SearchOverview` is the only thing the model generates for a search: a short
explanation of what the matching code does, the file to open first, and what
to read after it. Like `CodeSummary`, its JSON field names are camelCase and
every string and list is length-limited, so a rambling answer fails
validation instead of reaching the browser. The frontend shows it as plain
text.

`SearchOverviewContext` is everything one request may tell the model. It is
built from what the analysis already stores (search ranking, symbol names,
docstrings, imports) plus verified per-file AI summaries that are already
cached. No source file is downloaded for an overview.
"""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from repolens.ai.models import ParagraphText, RepoPath, SentenceText, _CamelModel


# Bump when `SearchOverview` changes shape, so cached overviews in the old
# shape are no longer served.
SEARCH_SCHEMA_VERSION = "1"

# How many top results an overview covers.
OVERVIEW_RESULT_LIMIT = 8


class ReadingStep(_CamelModel):
    """One file to read, and why, in the overview's suggested order."""

    path: RepoPath
    reason: SentenceText


class SearchOverview(_CamelModel):
    """The model's overview of one search's top results."""

    summary: ParagraphText
    start_here: ReadingStep
    read_next: Annotated[list[ReadingStep], Field(max_length=4)]
    uncertainties: Annotated[list[SentenceText], Field(max_length=2)]


@dataclass(frozen=True)
class SearchContextFile:
    """One search result, as given to the model and the validator.

    `imports_within` lists the other results this file imports, from the
    analyzed graph. `ai_summary` is the file's verified, already-cached AI
    summary, if there is one.
    """

    path: str
    position: int
    reason: str
    order_reason: str
    symbols: tuple[str, ...]
    docstring: str
    imports_within: tuple[str, ...]
    ai_summary: str | None = None


@dataclass(frozen=True)
class SearchOverviewContext:
    """Everything one overview request may tell the model about one search.

    `query_norm` is the normalized query used as the cache key, and
    `results_hash` identifies the ordered top results: a different ranking
    is a different overview.
    """

    query: str
    query_norm: str
    intent: str | None
    files: tuple[SearchContextFile, ...]
    results_hash: str
    total_results: int

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.files)

    @property
    def used_file_summaries(self) -> tuple[str, ...]:
        """Paths whose cached AI summary went into the context."""
        return tuple(item.path for item in self.files if item.ai_summary)

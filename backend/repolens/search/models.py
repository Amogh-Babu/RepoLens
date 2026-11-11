from dataclasses import dataclass
from typing import Literal


MatchKind = Literal[
    "filename", "symbol", "member", "reference", "docstring", "comment", "semantic"
]


@dataclass(frozen=True)
class SearchDocument:
    """Everything search can match in one file.

    `symbols` are module-level names; `members` are methods and class-level
    attributes written as `Owner.name`; `docstrings` and `comments` are prose.
    """

    path: str
    symbols: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()
    depended_on_by: tuple[str, ...] = ()
    members: tuple[str, ...] = ()
    docstrings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchEvidence:
    kind: MatchKind
    value: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class RankedFile:
    """One search result.

    `reason` says why the file matched; `order_reason` says why it sits at
    its place in the suggested reading order.
    """

    path: str
    score: float
    reason: str
    matches: tuple[MatchEvidence, ...]
    order_reason: str = ""


@dataclass(frozen=True)
class SearchPage:
    results: tuple[RankedFile, ...]
    total: int
    offset: int
    limit: int
    has_more: bool
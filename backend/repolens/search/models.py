from dataclasses import dataclass
from typing import Literal


MatchKind = Literal["filename", "symbol", "reference", "comment"]


@dataclass(frozen=True)
class SearchDocument:
    path: str
    symbols: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()
    depended_on_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchEvidence:
    kind: MatchKind
    value: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class RankedFile:
    path: str
    score: float
    reason: str
    matches: tuple[MatchEvidence, ...]


@dataclass(frozen=True)
class SearchPage:
    results: tuple[RankedFile, ...]
    total: int
    offset: int
    limit: int
    has_more: bool
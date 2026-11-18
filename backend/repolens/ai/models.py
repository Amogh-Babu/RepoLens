"""Data models for AI file summaries.

`CodeSummary` is the only thing the model generates. Its JSON field names are
camelCase, like every other API response, and every string and list is
length-limited, so a model answer that rambles, or one that smuggles in a
large blob, fails validation instead of reaching the browser. Text is shown as
plain text by the frontend; no generated field is ever rendered as HTML.

Everything about where a summary came from (analysis, path, commit, model,
prompt version, source hash, timestamps) lives in `SummaryMetadata`, which
RepoLens fills in itself and the model never sees as output.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


# Bump when `CodeSummary` changes shape, so cached summaries in the old shape
# are no longer served.
SCHEMA_VERSION = "1"

Coverage = Literal["complete", "partial"]
KeySymbolKind = Literal["function", "class", "variable", "method", "attribute"]
Relationship = Literal["imports", "importedBy"]
SideEffectKind = Literal[
    "database", "filesystem", "network", "subprocess", "environment", "other"
]

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SentenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
]
ParagraphText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
RepoPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
Line = Annotated[int, Field(ge=1)]


class _CamelModel(BaseModel):
    """Base model: camelCase JSON, unknown fields rejected."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )


class KeySymbol(_CamelModel):
    """A function, class, or member the summary calls out.

    `name` is a top-level name (`login`) or a member as `Owner.name`
    (`Session.refresh`). Validation requires it to exist in the file's
    syntax tree with the same kind and line.
    """

    name: Name
    kind: KeySymbolKind
    description: SentenceText
    line: Line


class SummaryDependency(_CamelModel):
    """An internal file this file imports, or that imports it.

    Validation requires the edge to exist in the analyzed dependency graph.
    """

    path: RepoPath
    relationship: Relationship
    description: SentenceText


class SideEffect(_CamelModel):
    """An observable effect the code performs, cited to its source lines."""

    kind: SideEffectKind
    description: SentenceText
    start_line: Line
    end_line: Line


class Evidence(_CamelModel):
    """A source line range that supports a claim in the summary."""

    start_line: Line
    end_line: Line
    description: SentenceText


class CodeSummary(_CamelModel):
    """The structured summary of one source file, as the model returns it."""

    summary: SentenceText
    purpose: ParagraphText
    responsibilities: Annotated[list[SentenceText], Field(min_length=1, max_length=5)]
    key_symbols: Annotated[list[KeySymbol], Field(max_length=12)]
    dependencies: Annotated[list[SummaryDependency], Field(max_length=15)]
    side_effects: Annotated[list[SideEffect], Field(max_length=10)]
    uncertainties: Annotated[list[SentenceText], Field(max_length=6)]
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=12)]
    coverage: Coverage


@dataclass(frozen=True)
class ContextSymbol:
    """A symbol from the syntax tree, as given to the model and validator.

    `name` is the top-level name or `Owner.member` for a class member;
    `end_line` is where its definition ends (equal to `line` when unknown).
    """

    name: str
    kind: KeySymbolKind
    line: int
    end_line: int


@dataclass(frozen=True)
class ContextImport:
    """An import from the syntax tree with its classification from the graph."""

    raw_name: str
    kind: str
    target_path: str | None
    line: int


@dataclass(frozen=True)
class CodeSummaryContext:
    """Everything one summary request may tell the model about one file.

    Source and metadata come from the same analyzed commit. `source` is the
    text actually sent (possibly a subset of the file); `inspected_lines`
    lists the 1-based, inclusive line ranges it covers, and `coverage` is
    `partial` whenever those ranges do not cover the whole file.
    """

    path: str
    language: str
    source: str
    symbols: tuple[ContextSymbol, ...]
    imports: tuple[ContextImport, ...]
    imported_by: tuple[str, ...]
    commit_sha: str
    source_hash: str
    coverage: Coverage
    line_count: int
    inspected_lines: tuple[tuple[int, int], ...]

    @property
    def internal_imports(self) -> tuple[str, ...]:
        """Return the repository files this file imports, per the graph."""
        return tuple(
            sorted(
                {
                    item.target_path
                    for item in self.imports
                    if item.kind == "internal" and item.target_path
                }
            )
        )


@dataclass(frozen=True)
class ProviderUsage:
    """Token counts the provider reported for one call, when it reports them."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResult:
    """A provider's raw structured answer, before RepoLens validates it."""

    payload: object
    model: str
    usage: ProviderUsage = ProviderUsage()

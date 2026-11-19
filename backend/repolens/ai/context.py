"""Build the bounded, line-numbered context for summarizing one file.

The symbols, imports, and importers come from RepoLens's own static analysis
(the stored graph, plus the existing `PythonAnalyzer` run on the downloaded
source); nothing here asks the model for structure. A file that fits the
input budget is sent whole. A larger one is cut on logical boundaries, never
mid-definition when avoidable: top-level statements first, then the methods
of an oversized class, and only when no definition fits at all, plain
line ranges from the top. Whatever
is left out is reported through `coverage="partial"` and `inspected_lines`.

The source is only parsed with `ast.parse`; it is never executed.
"""

import ast
from collections.abc import Iterable

from repolens.ai.errors import SourceMismatchError
from repolens.ai.models import (
    CodeSummaryContext,
    ContextImport,
    ContextSymbol,
    Coverage,
)
from repolens.ai.prompts import number_lines
from repolens.ai.source import hash_source
from repolens.analysis.models import ParsedFile
from repolens.graph.models import FileDetail


Span = tuple[int, int]


def build_context(
    *,
    detail: FileDetail,
    parsed: ParsedFile,
    source: str,
    max_input_chars: int,
) -> CodeSummaryContext:
    """Return the context for `detail.path`, bounded to `max_input_chars`.

    Args:
      detail: The file as stored by the analysis (symbols, imports, importers).
      parsed: The existing analyzer's result for the downloaded `source`.
      source: The file's text at the analyzed commit.
      max_input_chars: Budget for the numbered source text sent to the model.

    Raises:
      SourceMismatchError: The downloaded source does not match the stored
        analysis (different line count, parse result, or symbols), so it is
        not from the analyzed commit.
    """
    verify_same_commit(detail, parsed)
    lines = source.splitlines()
    line_count = len(lines)
    spans = _logical_units(source, line_count) if parsed.parsed else _line_units(line_count)
    inspected = _select_spans(lines, spans, max_input_chars)
    coverage: Coverage = "complete" if inspected == ((1, line_count),) or line_count == 0 else "partial"
    if line_count == 0:
        inspected = ()

    line_by_import = {item.raw_name: item.line for item in parsed.imports}
    return CodeSummaryContext(
        path=detail.path,
        language=parsed.language,
        source=_render(lines, inspected, line_count),
        symbols=_context_symbols(parsed, source),
        imports=tuple(
            ContextImport(
                raw_name=item.raw_name,
                kind=item.kind,
                target_path=item.target_path,
                line=line_by_import.get(item.raw_name, 0),
            )
            for item in detail.imports
        ),
        imported_by=tuple(detail.imported_by),
        commit_sha=detail.sha,
        source_hash=hash_source(source),
        coverage=coverage,
        line_count=line_count,
        inspected_lines=inspected,
    )


def verify_same_commit(detail: FileDetail, parsed: ParsedFile) -> None:
    """Raise unless the downloaded source matches the stored analysis.

    The download is pinned to the analyzed SHA, so a mismatch means GitHub
    returned something else; summarizing it would describe code the graph
    never saw.
    """
    if parsed.line_count != detail.line_count or parsed.parsed != detail.parsed:
        raise SourceMismatchError()
    stored = {(symbol.name, symbol.kind, symbol.line) for symbol in detail.symbols}
    fresh = {(symbol.name, symbol.kind, symbol.line) for symbol in parsed.symbols}
    if stored != fresh:
        raise SourceMismatchError()


def _context_symbols(parsed: ParsedFile, source: str) -> tuple[ContextSymbol, ...]:
    """Return top-level symbols and class members with their end lines."""
    if not parsed.parsed:
        return ()
    ends = _definition_ends(source)
    symbols = [
        ContextSymbol(
            name=symbol.name,
            kind=symbol.kind,
            line=symbol.line,
            end_line=ends.get((symbol.name, symbol.line), symbol.line),
        )
        for symbol in parsed.symbols
    ]
    symbols.extend(
        ContextSymbol(
            name=f"{member.owner}.{member.name}",
            kind=member.kind,
            line=member.line,
            end_line=ends.get((f"{member.owner}.{member.name}", member.line), member.line),
        )
        for member in parsed.members
    )
    return tuple(sorted(symbols, key=lambda item: (item.line, item.name)))


def _definition_ends(source: str) -> dict[tuple[str, int], int]:
    """Map (qualified name, line) of each def and class to its last line."""
    tree = ast.parse(source)
    ends: dict[tuple[str, int], int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ends[(node.name, node.lineno)] = node.end_lineno or node.lineno
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    key = (f"{node.name}.{child.name}", child.lineno)
                    ends[key] = child.end_lineno or child.lineno
    return ends


def _node_start(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", ())
    return min([node.lineno, *(item.lineno for item in decorators)])


def _covering_spans(nodes: Iterable[ast.stmt], first: int, last: int) -> list[Span]:
    """Split [first, last] into spans, one per node, attaching gaps forward.

    Comments and blank lines before a definition travel with it, and any
    trailing lines join the last span, so the spans tile the range exactly.
    """
    spans: list[Span] = []
    cursor = first
    for node in nodes:
        end = node.end_lineno or node.lineno
        if end < cursor:
            continue
        spans.append((cursor, end))
        cursor = end + 1
    if cursor <= last:
        if spans:
            start, _ = spans.pop()
            spans.append((start, last))
        else:
            spans.append((cursor, last))
    return spans


def _logical_units(source: str, line_count: int) -> list[list[Span]]:
    """Return candidate units: each is a list of spans, coarsest first.

    A unit is one top-level statement (with leading comments). For a class,
    the alternative split into its header and each member is kept too, so an
    oversized class can still be partly shown on method boundaries.
    """
    if line_count == 0:
        return []
    tree = ast.parse(source)
    units: list[list[Span]] = []
    # Top-level statements never overlap, so there is one span per statement.
    for span, node in zip(_covering_spans(tree.body, 1, line_count), tree.body):
        if isinstance(node, ast.ClassDef) and node.body:
            header_end = _node_start(node.body[0]) - 1
            members = _covering_spans(node.body, max(span[0], header_end + 1), span[1])
            header = [(span[0], header_end)] if header_end >= span[0] else []
            units.append([span, *header, *members])
        else:
            units.append([span])
    if not tree.body:
        units.append([(1, line_count)])
    return units


def _line_units(line_count: int) -> list[list[Span]]:
    """Units for a file that does not parse: every line on its own."""
    return [[(line, line)] for line in range(1, line_count + 1)]


def _cost(lines: list[str], span: Span) -> int:
    start, end = span
    return len(number_lines("\n".join(lines[start - 1 : end]), start)) + 1


def _select_spans(
    lines: list[str],
    units: list[list[Span]],
    budget: int,
) -> tuple[Span, ...]:
    """Keep whole units, in file order, while they fit the budget.

    A unit that does not fit is tried as its finer split (a class's header
    and members) and otherwise skipped, so a cut never falls inside a
    definition. Only when no logical unit fits at all (one huge function,
    say) is the file cut line by line from the top, as a last resort.
    """
    chosen: list[Span] = []
    remaining = budget
    for unit in units:
        whole, *parts = unit
        for candidate in [whole] if _cost(lines, whole) <= remaining else parts:
            cost = _cost(lines, candidate)
            if cost <= remaining:
                chosen.append(candidate)
                remaining -= cost
    if not chosen:
        for line in range(1, len(lines) + 1):
            cost = _cost(lines, (line, line))
            if cost > remaining:
                break
            chosen.append((line, line))
            remaining -= cost
    return _merge(chosen)


def _merge(spans: list[Span]) -> tuple[Span, ...]:
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _render(lines: list[str], spans: tuple[Span, ...], line_count: int) -> str:
    """Return the numbered text of `spans`, marking every omitted range."""
    blocks: list[str] = []
    cursor = 1
    for start, end in spans:
        if start > cursor:
            blocks.append(f"[lines {cursor}-{start - 1} omitted: not inspected]")
        blocks.append(number_lines("\n".join(lines[start - 1 : end]), start))
        cursor = end + 1
    if cursor <= line_count:
        blocks.append(f"[lines {cursor}-{line_count} omitted: not inspected]")
    return "\n".join(blocks)

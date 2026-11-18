"""Verify a model's summary against the file's source and static analysis.

These checks are structural. They prove that every named symbol, dependency,
cited line range, and backticked code name in a summary exists in what
RepoLens analyzed and sent; they reject invented functions, invented
dependencies, and citations outside the inspected source. They do not prove
that the prose describes the behavior correctly: a line range can exist and
still not support the sentence next to it. That is why the frontend labels
summaries as AI-generated and shows the evidence links, and why semantic
accuracy is measured separately (see `tests/fixtures/ai_reference`).
"""

from dataclasses import dataclass
import re
from typing import Any

from pydantic import ValidationError

from repolens.ai.models import CodeSummary, CodeSummaryContext


# A code name in backticks: `login`, `Session.refresh`, `load_config()`.
_BACKTICKED = re.compile(r"`([^`\n]{1,120})`")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_PROBLEMS = 12


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one model answer.

    `summary` is set only when `problems` is empty.
    """

    summary: CodeSummary | None
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.summary is not None and not self.problems


def validate_summary(payload: Any, context: CodeSummaryContext) -> ValidationResult:
    """Parse `payload` as a `CodeSummary` and check it against `context`.

    Problems are short, deterministic descriptions suitable for a repair
    prompt and for logs; they never include source text.
    """
    try:
        summary = CodeSummary.model_validate(payload)
    except ValidationError as error:
        return ValidationResult(None, _schema_problems(error))

    problems: list[str] = []
    problems.extend(_check_symbols(summary, context))
    problems.extend(_check_dependencies(summary, context))
    problems.extend(_check_ranges(summary, context))
    problems.extend(_check_code_names(summary, context))
    if context.coverage == "partial" and summary.coverage == "complete":
        problems.append(
            "coverage is 'complete' but only part of the file was provided; use 'partial'."
        )
    if problems:
        return ValidationResult(None, tuple(problems[:_MAX_PROBLEMS]))

    # Coverage is a fact about the request, not a judgment: record the real one.
    if summary.coverage != context.coverage:
        summary = summary.model_copy(update={"coverage": context.coverage})
    return ValidationResult(summary, ())


def _schema_problems(error: ValidationError) -> tuple[str, ...]:
    problems = []
    for item in error.errors()[:_MAX_PROBLEMS]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "answer"
        problems.append(f"{location}: {item.get('msg', 'invalid value')}.")
    return tuple(problems) or ("The answer did not match the required schema.",)


def _inspected(context: CodeSummaryContext, start: int, end: int) -> bool:
    return any(low <= start and end <= high for low, high in context.inspected_lines)


def _check_symbols(summary: CodeSummary, context: CodeSummaryContext) -> list[str]:
    known = {(symbol.name, symbol.kind): symbol.line for symbol in context.symbols}
    by_name: dict[str, list[str]] = {}
    for symbol in context.symbols:
        by_name.setdefault(symbol.name, []).append(symbol.kind)
    problems = []
    for item in summary.key_symbols:
        line = known.get((item.name, item.kind))
        if line is None:
            if item.name in by_name:
                problems.append(
                    f"keySymbols '{item.name}' is a {'/'.join(by_name[item.name])}, "
                    f"not a {item.kind}."
                )
            else:
                problems.append(
                    f"keySymbols '{item.name}' is not defined in this file's syntax tree."
                )
        elif item.line != line:
            problems.append(
                f"keySymbols '{item.name}' is defined on line {line}, not line {item.line}."
            )
        elif not _inspected(context, line, line):
            problems.append(
                f"keySymbols '{item.name}' (line {line}) is outside the inspected source."
            )
    return problems


def _check_dependencies(summary: CodeSummary, context: CodeSummaryContext) -> list[str]:
    allowed = {
        "imports": set(context.internal_imports),
        "importedBy": set(context.imported_by),
    }
    problems = []
    seen: set[tuple[str, str]] = set()
    for item in summary.dependencies:
        key = (item.path, item.relationship)
        if key in seen:
            problems.append(f"dependencies lists '{item.path}' ({item.relationship}) twice.")
            continue
        seen.add(key)
        if item.path not in allowed[item.relationship]:
            other = "importedBy" if item.relationship == "imports" else "imports"
            if item.path in allowed[other]:
                problems.append(
                    f"dependencies '{item.path}' has relationship '{other}', "
                    f"not '{item.relationship}'."
                )
            else:
                problems.append(
                    f"dependencies '{item.path}' is not an internal dependency "
                    "in the analyzed graph."
                )
    return problems


def _check_ranges(summary: CodeSummary, context: CodeSummaryContext) -> list[str]:
    cited = [("evidence", item.start_line, item.end_line) for item in summary.evidence]
    cited += [("sideEffects", item.start_line, item.end_line) for item in summary.side_effects]
    problems = []
    for field, start, end in cited:
        if start > end:
            problems.append(f"{field} range {start}-{end} starts after it ends.")
        elif end > context.line_count:
            problems.append(
                f"{field} range {start}-{end} is past the end of the file "
                f"({context.line_count} lines)."
            )
        elif not _inspected(context, start, end):
            problems.append(f"{field} range {start}-{end} cites lines that were not provided.")
    return problems


def _check_code_names(summary: CodeSummary, context: CodeSummaryContext) -> list[str]:
    """Reject backticked code names that appear nowhere in the inspected input.

    A name counts as present if it occurs as a word in the inspected source,
    or names a known symbol, import, or dependency path.
    """
    source_words = set(_IDENTIFIER.findall(context.source))
    known = {symbol.name for symbol in context.symbols}
    known |= {item.raw_name for item in context.imports}
    known |= set(context.internal_imports) | set(context.imported_by) | {context.path}
    problems = []
    reported: set[str] = set()
    for text in _prose(summary):
        for match in _BACKTICKED.finditer(text):
            name = match.group(1).strip()
            if name in known or name in reported:
                continue
            words = _IDENTIFIER.findall(name)
            missing = [word for word in words if word not in source_words]
            if words and missing:
                reported.add(name)
                problems.append(
                    f"The summary mentions `{name}`, but '{missing[0]}' does not "
                    "appear in the inspected source."
                )
    return problems


def _prose(summary: CodeSummary) -> list[str]:
    texts = [summary.summary, summary.purpose, *summary.responsibilities, *summary.uncertainties]
    texts += [item.description for item in summary.key_symbols]
    texts += [item.description for item in summary.dependencies]
    texts += [item.description for item in summary.side_effects]
    texts += [item.description for item in summary.evidence]
    return texts

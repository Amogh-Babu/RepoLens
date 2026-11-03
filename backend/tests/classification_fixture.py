"""Measure import classification against the hand-labeled fixtures (#34).

Each directory under `tests/fixtures/import_classification/` is one layout: a
`repo/` tree and an `expected.json` naming, for every analyzed file, the
classification every import in it must get. The labels were written from
Python's own import rules, not from RepoLens' output, so a reference the
classifier gets wrong stays labeled with the right answer and shows up as a
miss.

A *reference* is one `(file path, raw name)` pair, which is both the unit the
classifier emits and the unit this module scores. One statement can yield
several references (`from library.core import Engine, engine` reaches the
package and one of its submodules), and references to one target are merged
per file, so the reference count is not the statement count.

The fixtures are read and parsed like any analyzed repository; they are never
imported or executed.

Print the report from `backend/`:

    PYTHONPATH=. python3 tests/classification_fixture.py
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files


LAYOUTS_ROOT = Path(__file__).parent / "fixtures" / "import_classification"

# (kind, target): the target is a repository path for an internal import, the
# top-level package for an external one, and None when it is unresolved.
Classification = tuple[str, str | None]

# (repository-relative file path, the import's raw name).
Reference = tuple[str, str]


@dataclass(frozen=True)
class Miss:
    """One reference the classifier did not label the way the fixture does.

    `expected` is None for a reference the classifier emitted that the fixture
    does not label at all, and `actual` is None for a labeled reference the
    classifier never emitted.
    """

    path: str
    raw_name: str
    expected: Classification | None
    actual: Classification | None

    def describe(self) -> str:
        """Render the miss as one line for the report."""
        want = "no such reference" if self.expected is None else _render(self.expected)
        got = "nothing" if self.actual is None else _render(self.actual)
        return f"{self.path}: {self.raw_name} -- want {want}, got {got}"


@dataclass(frozen=True)
class LayoutReport:
    """The score for one fixture layout."""

    title: str
    expected_total: int
    correct: int
    expected_unresolved: int
    actual_total: int
    actual_unresolved: int
    misses: tuple[Miss, ...]

    @property
    def percent_correct(self) -> float:
        """Return the share of labeled references classified correctly."""
        return _percent(self.correct, self.expected_total)

    @property
    def percent_unresolved(self) -> float:
        """Return the share of emitted references left unresolved."""
        return _percent(self.actual_unresolved, self.actual_total)


def layout_names() -> tuple[str, ...]:
    """Return every fixture layout directory name, in a stable order."""
    return tuple(
        sorted(
            path.name
            for path in LAYOUTS_ROOT.iterdir()
            if path.is_dir() and (path / "expected.json").is_file()
        )
    )


def expected_classifications(layout: str) -> dict[Reference, Classification]:
    """Return the hand-labeled classification of every reference in `layout`."""
    return {
        (path, raw_name): (kind, target)
        for path, references in expectations(layout)["imports"].items()
        for raw_name, kind, target in references
    }


def actual_classifications(layout: str) -> dict[Reference, Classification]:
    """Return what the classifier reports for every reference in `layout`.

    The layout's `repo/` tree goes through the same three calls as the
    pipeline's parsing and classifying stages, so this measures the classifier
    as the pipeline uses it rather than through a hand-built file list.
    """
    return {
        (file.path, imported.raw_name): (
            imported.kind,
            imported.target_path or imported.target_package,
        )
        for file in classify_imports(to_analyzed_files(analyze_layout(layout)))
        for imported in file.imports
    }


def analyze_layout(layout: str):
    """Parse one layout's `repo/` tree with the default analyzers."""
    return AnalysisService().analyze_repository(LAYOUTS_ROOT / layout / "repo")


def expectations(layout: str) -> dict[str, Any]:
    """Read and return one layout's `expected.json`."""
    path = LAYOUTS_ROOT / layout / "expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


def measure_layout(layout: str) -> LayoutReport:
    """Score one layout's classifications against its hand-written labels."""
    expected = expected_classifications(layout)
    actual = actual_classifications(layout)

    mislabeled = tuple(
        Miss(path, raw_name, classification, actual.get((path, raw_name)))
        for (path, raw_name), classification in sorted(expected.items())
        if actual.get((path, raw_name)) != classification
    )
    unlabeled = tuple(
        Miss(path, raw_name, None, classification)
        for (path, raw_name), classification in sorted(actual.items())
        if (path, raw_name) not in expected
    )

    return LayoutReport(
        title=expectations(layout)["title"],
        expected_total=len(expected),
        correct=len(expected) - len(mislabeled),
        expected_unresolved=_count_unresolved(expected.values()),
        actual_total=len(actual),
        actual_unresolved=_count_unresolved(actual.values()),
        misses=mislabeled + unlabeled,
    )


def measure_all() -> dict[str, LayoutReport]:
    """Score every fixture layout, keyed by layout name."""
    return {layout: measure_layout(layout) for layout in layout_names()}


def overall(reports: Iterable[LayoutReport]) -> LayoutReport:
    """Return one report summing every layout's counts."""
    totals = tuple(reports)
    return LayoutReport(
        title="overall",
        expected_total=sum(report.expected_total for report in totals),
        correct=sum(report.correct for report in totals),
        expected_unresolved=sum(report.expected_unresolved for report in totals),
        actual_total=sum(report.actual_total for report in totals),
        actual_unresolved=sum(report.actual_unresolved for report in totals),
        misses=tuple(miss for report in totals for miss in report.misses),
    )


def format_report(reports: dict[str, LayoutReport]) -> str:
    """Render the per-layout and overall percentages as a printable report."""
    total = overall(reports.values())
    header = ("layout", "refs", "correct", "unresolved", "want unresolved")
    rows = tuple(_row_values(report) for report in (*reports.values(), total))
    widths = [max(len(row[column]) for row in (header, *rows)) for column in range(5)]
    rule = tuple("-" * width for width in widths)

    lines = [
        "Import classification against hand-labeled fixtures",
        "",
        _row(header, widths),
        _row(rule, widths),
        *(_row(row, widths) for row in rows[:-1]),
        _row(rule, widths),
        _row(rows[-1], widths),
        "",
        f"Misses ({len(total.misses)}):",
    ]
    if total.misses:
        lines.extend(f"  {miss.describe()}" for miss in total.misses)
    else:
        lines.append("  none")
    return "\n".join(lines)


def _row_values(report: LayoutReport) -> tuple[str, ...]:
    """Render one layout's counts and percentages as report cells."""
    return (
        report.title,
        str(report.expected_total),
        f"{report.correct} ({report.percent_correct:.1f}%)",
        f"{report.actual_unresolved} ({report.percent_unresolved:.1f}%)",
        str(report.expected_unresolved),
    )


def _row(values: tuple[str, ...], widths: list[int]) -> str:
    """Render one row, left-aligning the layout and right-aligning the counts."""
    cells = [values[0].ljust(widths[0])]
    cells.extend(value.rjust(width) for value, width in zip(values[1:], widths[1:]))
    return "  ".join(cells).rstrip()


def _count_unresolved(classifications: Iterable[Classification]) -> int:
    """Count the classifications whose kind is `unresolved`."""
    return sum(1 for kind, _ in classifications if kind == "unresolved")


def _percent(part: int, whole: int) -> float:
    """Return `part` as a percentage of `whole`, and 100.0 for an empty whole."""
    return 100.0 if whole == 0 else 100.0 * part / whole


def _render(classification: Classification) -> str:
    """Render one classification as `kind` or `kind target`."""
    kind, target = classification
    return kind if target is None else f"{kind} {target}"


if __name__ == "__main__":
    print(format_report(measure_all()))

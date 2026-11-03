"""Measure import classification against hand-labeled fixture layouts.

This answers one question for issue #34 (Risk 2): of the imports a repository
writes, how many does `repolens.analysis.classify_imports` label correctly,
and how many does it leave unresolved? Nothing here changes the classifier;
the numbers are reported as measured.

Each directory under `tests/fixtures/import_classification/` is one layout: a
`repo/` tree and an `expected.json` naming, for every analyzed file, the
classification every import in it must get. The labels were written from
Python's own import rules -- the rules `tests/fixtures/import_classification/
README.md` states -- and not from RepoLens' output, so a reference the
classifier gets wrong keeps the right label and is reported as a miss.

A *reference* is one `(file path, raw name)` pair, which is both the unit the
classifier emits and the unit this module scores. One statement can yield
several references (`from library.core import Engine, engine` reaches the
package and one of its submodules), and references to one target are merged
per file, so the reference count is not the statement count.

Classification is measured through the pipeline's own calls:
`AnalysisService` parses the tree and `classify_imports` resolves its imports,
the same sequence `PipelineAnalysisRunner` performs for a real repository. No
fixture file is imported or executed.

Run it from `backend/`:

    python -m benchmarks.import_classification            # print the table
    python -m benchmarks.import_classification --write    # refresh the record
"""

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files


BENCHMARK_ROOT = Path(__file__).parent
BACKEND_ROOT = BENCHMARK_ROOT.parent
LAYOUTS_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "import_classification"
RECORD_PATH = BENCHMARK_ROOT / "measured_classification.json"

# (kind, target): the target is a repository path for an internal import, the
# top-level package for an external one, and None when it is unresolved.
Classification = tuple[str, str | None]

# (repository-relative file path, the import's raw name).
Reference = tuple[str, str]


@dataclass(frozen=True)
class Miss:
    """One reference the classifier did not label the way the fixture does.

    `expected` is None for a reference the classifier emitted that the fixture
    labels nowhere, and `actual` is None for a labeled reference the
    classifier never emitted.
    """

    layout: str
    path: str
    raw_name: str
    expected: Classification | None
    actual: Classification | None

    def describe(self) -> str:
        """Render the miss as one line for the report."""
        want = "no such reference" if self.expected is None else render(self.expected)
        got = "nothing" if self.actual is None else render(self.actual)
        return f"{self.path}: {self.raw_name} -- want {want}, got {got}"


@dataclass(frozen=True)
class LayoutScore:
    """What the classifier got right and wrong on one fixture layout."""

    layout: str
    title: str
    labeled: int
    correct: int
    labeled_unresolved: int
    classified: int
    classified_unresolved: int
    misses: tuple[Miss, ...]

    @property
    def percent_correct(self) -> float:
        """Return the share of labeled references classified correctly."""
        return percent(self.correct, self.labeled)

    @property
    def percent_unresolved(self) -> float:
        """Return the share of emitted references left unresolved."""
        return percent(self.classified_unresolved, self.classified)


@dataclass(frozen=True)
class Measurement:
    """Every layout's score, plus the totals across them."""

    scores: tuple[LayoutScore, ...]

    @property
    def misses(self) -> tuple[Miss, ...]:
        """Return every miss, layout by layout."""
        return tuple(miss for score in self.scores for miss in score.misses)

    @property
    def total(self) -> LayoutScore:
        """Return one score summing every layout's counts."""
        return LayoutScore(
            layout="overall",
            title="overall",
            labeled=sum(score.labeled for score in self.scores),
            correct=sum(score.correct for score in self.scores),
            labeled_unresolved=sum(score.labeled_unresolved for score in self.scores),
            classified=sum(score.classified for score in self.scores),
            classified_unresolved=sum(
                score.classified_unresolved for score in self.scores
            ),
            misses=self.misses,
        )


def layout_names() -> tuple[str, ...]:
    """Return every fixture layout directory name, in a stable order."""
    return tuple(
        sorted(
            path.name
            for path in LAYOUTS_ROOT.iterdir()
            if path.is_dir() and (path / "expected.json").is_file()
        )
    )


def expectations(layout: str) -> dict[str, Any]:
    """Read and return one layout's `expected.json`."""
    return json.loads(
        (LAYOUTS_ROOT / layout / "expected.json").read_text(encoding="utf-8")
    )


def analyze_layout(layout: str):
    """Parse one layout's `repo/` tree with the default analyzers."""
    return AnalysisService().analyze_repository(LAYOUTS_ROOT / layout / "repo")


def expected_classifications(layout: str) -> dict[Reference, Classification]:
    """Return the hand-labeled classification of every reference in `layout`."""
    return {
        (path, raw_name): (kind, target)
        for path, references in expectations(layout)["imports"].items()
        for raw_name, kind, target in references
    }


def actual_classifications(layout: str) -> dict[Reference, Classification]:
    """Return what the classifier reports for every reference in `layout`."""
    return {
        (file.path, imported.raw_name): (
            imported.kind,
            imported.target_path or imported.target_package,
        )
        for file in classify_imports(to_analyzed_files(analyze_layout(layout)))
        for imported in file.imports
    }


def score_layout(layout: str) -> LayoutScore:
    """Score one layout's classifications against its hand-written labels."""
    expected = expected_classifications(layout)
    actual = actual_classifications(layout)

    mislabeled = tuple(
        Miss(layout, path, raw_name, classification, actual.get((path, raw_name)))
        for (path, raw_name), classification in sorted(expected.items())
        if actual.get((path, raw_name)) != classification
    )
    unlabeled = tuple(
        Miss(layout, path, raw_name, None, classification)
        for (path, raw_name), classification in sorted(actual.items())
        if (path, raw_name) not in expected
    )

    return LayoutScore(
        layout=layout,
        title=expectations(layout)["title"],
        labeled=len(expected),
        correct=len(expected) - len(mislabeled),
        labeled_unresolved=count_unresolved(expected.values()),
        classified=len(actual),
        classified_unresolved=count_unresolved(actual.values()),
        misses=mislabeled + unlabeled,
    )


def measure() -> Measurement:
    """Score every fixture layout."""
    return Measurement(tuple(score_layout(layout) for layout in layout_names()))


def to_record(measurement: Measurement) -> dict:
    """Describe a measurement as the JSON the recorded results file holds."""
    return {
        "overall": _score_record(measurement.total),
        "layouts": [
            {"layout": score.layout, **_score_record(score)}
            for score in measurement.scores
        ],
        "misses": [
            {
                "layout": miss.layout,
                "path": miss.path,
                "rawName": miss.raw_name,
                "expected": _classification_record(miss.expected),
                "actual": _classification_record(miss.actual),
            }
            for miss in measurement.misses
        ],
    }


def load_record(record_path: Path = RECORD_PATH) -> dict:
    """Read the recorded measurement the test compares a fresh run against."""
    return json.loads(record_path.read_text(encoding="utf-8"))


def write_record(measurement: Measurement, record_path: Path = RECORD_PATH) -> None:
    """Overwrite the recorded measurement with a fresh one."""
    record_path.write_text(
        json.dumps(to_record(measurement), indent=2) + "\n", encoding="utf-8"
    )


def format_report(measurement: Measurement) -> str:
    """Render the per-layout and overall percentages as a printable table."""
    header = (
        f"{'layout':<28}{'refs':>6}{'correct':>16}"
        f"{'unresolved':>16}{'labeled unres.':>16}"
    )
    rule = "-" * len(header)

    lines = [
        "Import classification against hand-labeled fixtures",
        "",
        header,
        rule,
    ]
    lines.extend(_report_row(score) for score in measurement.scores)
    lines.append(rule)
    lines.append(_report_row(measurement.total))

    lines.extend(["", f"Misses ({len(measurement.misses)}):"])
    if measurement.misses:
        lines.extend(
            f"  [{miss.layout}] {miss.describe()}" for miss in measurement.misses
        )
    else:
        lines.append("  none")
    return "\n".join(lines)


def count_unresolved(classifications: Iterable[Classification]) -> int:
    """Count the classifications whose kind is `unresolved`."""
    return sum(1 for kind, _ in classifications if kind == "unresolved")


def percent(part: int, whole: int) -> float:
    """Return `part` as a percentage of `whole`, and 100.0 for an empty whole."""
    return 100.0 if whole == 0 else 100.0 * part / whole


def render(classification: Classification) -> str:
    """Render one classification as `kind` or `kind target`."""
    kind, target = classification
    return kind if target is None else f"{kind} {target}"


def _report_row(score: LayoutScore) -> str:
    """Render one layout's counts and percentages as a table row."""
    correct = f"{score.correct} ({score.percent_correct:.1f}%)"
    unresolved = f"{score.classified_unresolved} ({score.percent_unresolved:.1f}%)"
    return (
        f"{score.title:<28}{score.labeled:>6}{correct:>16}"
        f"{unresolved:>16}{score.labeled_unresolved:>16}"
    )


def _score_record(score: LayoutScore) -> dict:
    """Describe one layout's score as JSON."""
    return {
        "title": score.title,
        "labeledReferences": score.labeled,
        "correct": score.correct,
        "percentCorrect": round(score.percent_correct, 4),
        "classifiedReferences": score.classified,
        "unresolved": score.classified_unresolved,
        "percentUnresolved": round(score.percent_unresolved, 4),
        "labeledUnresolved": score.labeled_unresolved,
    }


def _classification_record(classification: Classification | None) -> dict | None:
    """Describe one side of a miss as JSON, or None when there is no record."""
    if classification is None:
        return None
    kind, target = classification
    return {"kind": kind, "target": target}


def main(argv: list[str] | None = None) -> int:
    """Print the accuracy table, optionally refreshing the recorded results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"overwrite {RECORD_PATH.name} with the measured numbers",
    )
    args = parser.parse_args(argv)

    measurement = measure()
    print(format_report(measurement))
    if args.write:
        write_record(measurement)
        print(f"Wrote {RECORD_PATH.relative_to(BACKEND_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

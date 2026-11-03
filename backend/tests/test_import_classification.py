"""Reproduce the import classification measurement (issue #34, Risk 2).

These tests do two jobs. First they check the measurement is sound: every
layout is labeled, every analyzed file has an entry, every label names a kind
and target that are well formed, and every internal target is a file the
layout actually contains -- so the classifier cannot be scored against labels
that are themselves impossible. Then they re-run the whole measurement and
compare it with `benchmarks/measured_classification.json`, so a classifier
change that moves the numbers fails here instead of going unnoticed.

The one recorded miss is a real classifier error, kept as a miss on purpose:
`main.py` writes `import app.config.defaults` where `app/config.py` shadows
the `app/config/` directory, and CPython raises
`ModuleNotFoundError: ... 'app.config' is not a package`. The fixture keeps
the correct label (`unresolved`) and this test asserts the classifier still
gets it wrong, so fixing the classifier fails here and the fixture does not
have to change. Do not relabel the fixture to make this pass.

Refresh the recorded numbers deliberately, from `backend/`:

    python -m benchmarks.import_classification --write
"""

import sys

import pytest

from benchmarks.import_classification import (
    LAYOUTS_ROOT,
    Measurement,
    actual_classifications,
    analyze_layout,
    expectations,
    expected_classifications,
    format_report,
    layout_names,
    load_record,
    measure,
    to_record,
)


LAYOUTS = layout_names()

# The layouts issue #34 asks for, each a directory under LAYOUTS_ROOT.
EXPECTED_LAYOUTS = (
    "external_packages",
    "module_directory_collision",
    "monorepo_source_roots",
    "namespace_packages",
    "reexports",
    "relative_imports",
    "src_layout",
)

# The one reference the classifier gets wrong, as (layout, path, raw name).
KNOWN_MISS = ("module_directory_collision", "main.py", "app.config.defaults")

VALID_KINDS = frozenset({"internal", "external", "unresolved"})


@pytest.fixture(scope="module")
def measurement() -> Measurement:
    """Measure once; every test below reads the same run."""
    return measure()


def test_every_layout_issue_34_asks_for_is_present() -> None:
    assert LAYOUTS == EXPECTED_LAYOUTS
    for layout in LAYOUTS:
        assert (LAYOUTS_ROOT / layout / "repo").is_dir(), layout
        assert expectations(layout)["title"], layout
        assert expectations(layout)["summary"], layout


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_analyzed_file_is_labeled(layout: str) -> None:
    """A file with no entry would silently drop its imports from the score."""
    labeled = set(expectations(layout)["imports"])
    analyzed = {parsed.path for parsed in analyze_layout(layout).files}

    assert analyzed == labeled, f"{layout}: {analyzed ^ labeled}"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_label_is_well_formed(layout: str) -> None:
    """A label names a valid kind, and a target only where a target belongs."""
    for (path, raw_name), (kind, target) in expected_classifications(layout).items():
        where = f"{layout}:{path}:{raw_name}"
        assert kind in VALID_KINDS, where
        assert raw_name, where
        if kind == "unresolved":
            assert target is None, where
        else:
            assert target, where


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_internal_label_points_at_a_file_the_layout_contains(
    layout: str,
) -> None:
    """An internal label naming no real file could never be satisfied."""
    repo = LAYOUTS_ROOT / layout / "repo"

    for (path, raw_name), (kind, target) in expected_classifications(layout).items():
        if kind == "internal":
            assert (repo / target).is_file(), f"{layout}:{path}:{raw_name} -> {target}"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_the_classifier_emits_a_classification_for_every_labeled_reference(
    layout: str,
) -> None:
    """Scoring is only meaningful while both sides cover the same references."""
    expected = set(expected_classifications(layout))
    actual = set(actual_classifications(layout))

    assert expected == actual, f"{layout}: {expected ^ actual}"


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_classification_is_left_as_the_parser_reported_it(layout: str) -> None:
    """Every import reaches the classifier: an internal kind needs a target."""
    for (path, raw_name), (kind, target) in actual_classifications(layout).items():
        where = f"{layout}:{path}:{raw_name}"
        assert kind in VALID_KINDS, where
        assert (target is None) == (kind == "unresolved"), where


def test_the_measurement_reproduces_the_recorded_numbers(
    measurement: Measurement,
) -> None:
    """The whole report, per layout and overall, matches what was recorded."""
    assert to_record(measurement) == load_record()


def test_overall_accuracy_is_84_of_85_references(measurement: Measurement) -> None:
    """Spelled out, so a change to the recorded file alone cannot hide drift."""
    total = measurement.total

    assert (total.correct, total.labeled) == (84, 85)
    assert round(total.percent_correct, 1) == 98.8
    assert (total.classified_unresolved, total.classified) == (3, 85)
    assert round(total.percent_unresolved, 1) == 3.5
    assert total.labeled_unresolved == 4


def test_every_layout_but_the_collision_classifies_perfectly(
    measurement: Measurement,
) -> None:
    perfect = {
        score.layout for score in measurement.scores if score.correct == score.labeled
    }

    assert perfect == set(EXPECTED_LAYOUTS) - {"module_directory_collision"}


def test_the_only_miss_is_the_known_classifier_error(
    measurement: Measurement,
) -> None:
    """`import app.config.defaults` is a ModuleNotFoundError, not an edge.

    `app/config.py` wins the `app.config` name over the `app/config/`
    directory, so nothing can be imported beneath it. The classifier resolves
    the name to `app/config/defaults.py` anyway. Fix the classifier rather
    than this label.
    """
    assert len(measurement.misses) == 1
    miss = measurement.misses[0]

    assert (miss.layout, miss.path, miss.raw_name) == KNOWN_MISS
    assert miss.expected == ("unresolved", None)
    assert miss.actual == ("internal", "app/config/defaults.py")


def test_the_report_states_the_percentages_per_layout_and_overall(
    measurement: Measurement,
) -> None:
    report = format_report(measurement)

    for score in measurement.scores:
        assert score.title in report
    assert "overall" in report
    assert "84 (98.8%)" in report
    assert "3 (3.5%)" in report
    assert "app.config.defaults" in report


def test_measuring_the_fixtures_does_not_import_them() -> None:
    """The layouts are parsed as data; nothing in them is ever executed."""
    measure()

    assert not {
        name
        for name in sys.modules
        if name.split(".")[0]
        in {"shopfront", "telemetry", "library", "store", "app", "pkg", "service_a"}
    }
    assert not [path for path in sys.path if "import_classification" in path]

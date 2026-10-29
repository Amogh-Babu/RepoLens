"""Tests that filtered files never reach a LanguageAnalyzer (#26).

`AnalysisService` consumes the ingestion `FileFilter`, so these tests record
every path handed to an analyzer and assert the excluded ones are absent. The
fixture tree is only read and parsed; it is never imported or executed.
"""

from pathlib import Path

from repolens.analysis import (
    AnalysisService,
    ParsedFile,
    PythonAnalyzer,
    to_analysis_counts,
)
from repolens.ingestion import ArchiveLimits, FileExclusion, SourceFileFilter


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "filter_mini_repo"

OWN_SOURCE_PATHS = [
    "app/__init__.py",
    "app/bulk_table.py",
    "app/helpers.py",
    "app/main.py",
]


class RecordingAnalyzer:
    """A `LanguageAnalyzer` that records every file it is asked to analyze."""

    language = "python"
    file_extensions = (".py", ".pyi")

    def __init__(self) -> None:
        self.analyzed_paths: list[str] = []
        self._analyzer = PythonAnalyzer()

    def supports(self, path: str) -> bool:
        return path.endswith(self.file_extensions)

    def analyze(self, path: str, source: str) -> ParsedFile:
        self.analyzed_paths.append(path)
        return self._analyzer.analyze(path, source)


class AllowEverythingFilter:
    """A `FileFilter` that excludes nothing, for the unfiltered comparison."""

    def exclusion_for(
        self, path: str, size_bytes: int | None = None
    ) -> FileExclusion | None:
        return None

    def directory_exclusion_for(self, path: str) -> FileExclusion | None:
        return None


def _write(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_the_default_service_filters_vendored_and_generated_files() -> None:
    analyzer = RecordingAnalyzer()

    analysis = AnalysisService((analyzer,)).analyze_repository(FIXTURE_ROOT)

    assert [parsed.path for parsed in analysis.files] == OWN_SOURCE_PATHS
    assert analyzer.analyzed_paths == OWN_SOURCE_PATHS
    assert analysis.skipped_paths == (
        "README.md",
        "app/schema_pb2.py",
        "app/settings_generated.py",
        "docs/notes.md",
        "package-lock.json",
        "static/app.min.js",
    )


def test_without_a_filter_the_same_tree_reaches_the_analyzer() -> None:
    analyzer = RecordingAnalyzer()
    service = AnalysisService((analyzer,), file_filter=AllowEverythingFilter())

    analysis = service.analyze_repository(FIXTURE_ROOT)

    assert "vendor/leftpad/leftpad.py" in analyzer.analyzed_paths
    assert "build/bundled_app.py" in analyzer.analyzed_paths
    assert "app/schema_pb2.py" in analyzer.analyzed_paths
    assert analysis.get("third_party/parser/parse.py") is not None


def test_an_oversized_file_is_skipped_instead_of_analyzed() -> None:
    analyzer = RecordingAnalyzer()
    service = AnalysisService(
        (analyzer,),
        file_filter=SourceFileFilter(ArchiveLimits(max_file_bytes=1_024)),
    )

    analysis = service.analyze_repository(FIXTURE_ROOT)

    assert "app/bulk_table.py" not in analyzer.analyzed_paths
    assert "app/bulk_table.py" in analysis.skipped_paths
    assert analysis.get("app/bulk_table.py") is None
    assert "app/main.py" in analyzer.analyzed_paths


def test_a_vendored_directory_is_pruned_rather_than_reported_file_by_file(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    for index in range(3):
        _write(tmp_path, f"node_modules/dep/module{index}.py", "VALUE = 1\n")
    _write(tmp_path, "docs/notes.md", "# Notes\n")

    analysis = AnalysisService().analyze_repository(tmp_path)

    assert [parsed.path for parsed in analysis.files] == ["app/main.py"]
    assert analysis.skipped_paths == ("docs/notes.md",)


def test_an_injected_filter_replaces_the_default_rules(tmp_path: Path) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    _write(tmp_path, "app/legacy/old.py", "VALUE = 1\n")
    _write(tmp_path, "vendor/dep/dep.py", "VALUE = 2\n")
    analyzer = RecordingAnalyzer()
    service = AnalysisService(
        (analyzer,),
        file_filter=SourceFileFilter(extra_excluded_directories=("legacy",)),
    )

    analysis = service.analyze_repository(tmp_path)

    assert analyzer.analyzed_paths == ["app/main.py"]
    assert analysis.skipped_paths == ()
    assert analysis.parsed_count == 1


def test_filtered_files_are_counted_as_excluded_for_the_graph_store(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    _write(tmp_path, "app/schema_pb2.py", "SCHEMA = 1\n")
    _write(tmp_path, "README.md", "# Readme\n")

    analysis = AnalysisService().analyze_repository(tmp_path)
    counts = to_analysis_counts(analysis)

    assert (counts.analyzed, counts.excluded, counts.unparsed) == (1, 2, 0)

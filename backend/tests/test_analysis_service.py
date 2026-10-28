"""Tests for AnalysisService: analyzer dispatch and repository walks (#22)."""

from pathlib import Path

import pytest

from repolens.analysis import (
    AnalysisService,
    LanguageAnalyzer,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    PythonAnalyzer,
    UnsupportedFileError,
    to_analysis_counts,
)


class StubTypeScriptAnalyzer:
    """A second-language analyzer, standing in for a future real one.

    It exists to show that another language plugs in behind
    `LanguageAnalyzer` without changes to `AnalysisService`.
    """

    language = "typescript"
    file_extensions = (".ts",)

    def supports(self, path: str) -> bool:
        return path.endswith(self.file_extensions)

    def analyze(self, path: str, source: str) -> ParsedFile:
        lines = source.splitlines()
        return ParsedFile(
            path=path,
            language=self.language,
            line_count=len(lines),
            imports=tuple(
                ParsedImport(
                    module=line.split("'")[1],
                    form="from",
                    symbols=("default",),
                    line=number,
                )
                for number, line in enumerate(lines, start=1)
                if line.startswith("import ")
            ),
            symbols=tuple(
                ParsedSymbol(
                    name=line.removeprefix("export function ").split("(")[0],
                    kind="function",
                    line=number,
                )
                for number, line in enumerate(lines, start=1)
                if line.startswith("export function ")
            ),
        )


def _write(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_default_service_analyzes_python() -> None:
    service = AnalysisService()

    assert service.languages == ("python",)
    assert isinstance(service.analyzers[0], PythonAnalyzer)
    assert service.supports("app/main.py")
    assert not service.supports("app/main.ts")


def test_a_second_language_analyzer_plugs_in_without_changing_the_service() -> None:
    service = AnalysisService((PythonAnalyzer(), StubTypeScriptAnalyzer()))

    assert service.languages == ("python", "typescript")
    assert isinstance(service.analyzer_for("web/app.ts"), StubTypeScriptAnalyzer)
    assert isinstance(service.analyzer_for("app/main.py"), PythonAnalyzer)
    assert service.analyzer_for("README.md") is None
    assert all(isinstance(analyzer, LanguageAnalyzer) for analyzer in service.analyzers)

    parsed = service.analyze_source(
        "web/app.ts",
        "import { client } from './client';\nexport function render() {}\n",
    )

    assert parsed.language == "typescript"
    assert [imported.raw_name for imported in parsed.imports] == ["./client"]
    assert [symbol.name for symbol in parsed.symbols] == ["render"]


def test_analyzing_an_unsupported_file_raises_unsupported_file_error() -> None:
    service = AnalysisService()

    with pytest.raises(UnsupportedFileError) as error:
        service.analyze_source("docs/notes.md", "# Notes\n")

    assert error.value.path == "docs/notes.md"


def test_analyze_repository_reports_imports_and_symbols_per_file(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/__init__.py", '"""App."""\n')
    _write(
        tmp_path,
        "app/main.py",
        "import os\n\nfrom .service import run\n\nVERSION = '1'\n",
    )
    _write(tmp_path, "app/service.py", "def run() -> None:\n    pass\n")
    _write(tmp_path, "README.md", "# Readme\n")

    analysis = AnalysisService().analyze_repository(tmp_path)

    assert [parsed.path for parsed in analysis.files] == [
        "app/__init__.py",
        "app/main.py",
        "app/service.py",
    ]
    assert analysis.skipped_paths == ("README.md",)
    assert analysis.parsed_count == 3
    assert analysis.unparsed_count == 0

    main = analysis.get("app/main.py")
    assert main is not None
    assert [imported.raw_name for imported in main.imports] == ["os", ".service"]
    assert [symbol.name for symbol in main.symbols] == ["VERSION"]
    assert analysis.get("app/missing.py") is None


def test_analyze_repository_skips_metadata_and_build_directories(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    _write(tmp_path, "__pycache__/main.cpython-313.pyc", "not source\n")
    _write(tmp_path, ".git/hooks/pre-commit.py", "import os\n")
    _write(tmp_path, "app/__pycache__/main.cpython-313.py", "import os\n")

    analysis = AnalysisService().analyze_repository(tmp_path)

    assert [parsed.path for parsed in analysis.files] == ["app/main.py"]
    assert analysis.skipped_paths == ()


def test_analyze_repository_does_not_follow_symlinks(tmp_path: Path) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    (tmp_path / "link.py").symlink_to(tmp_path / "app" / "main.py")
    (tmp_path / "app" / "loop").symlink_to(tmp_path, target_is_directory=True)

    analysis = AnalysisService().analyze_repository(tmp_path)

    assert [parsed.path for parsed in analysis.files] == ["app/main.py"]


def test_unparsable_files_are_reported_without_failing_the_analysis(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/good.py", "def run() -> None:\n    pass\n")
    _write(tmp_path, "app/broken.py", "def broken(:\n    pass\n")

    analysis = AnalysisService().analyze_repository(tmp_path)

    broken = analysis.get("app/broken.py")
    good = analysis.get("app/good.py")
    assert broken is not None and good is not None
    assert broken.parsed is False
    assert broken.error is not None
    assert good.parsed is True
    assert analysis.parsed_count == 1
    assert analysis.unparsed_count == 1


def test_a_file_that_is_not_utf8_is_reported_as_unparsed(tmp_path: Path) -> None:
    path = tmp_path / "app" / "latin1.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"VALUE = '\xff\xfe binary'\n")

    analysis = AnalysisService().analyze_repository(tmp_path)

    latin1 = analysis.get("app/latin1.py")
    assert latin1 is not None
    assert latin1.parsed is False
    assert latin1.error is not None
    assert "UTF-8" in latin1.error.message


def test_an_unreadable_file_is_reported_as_unparsed(tmp_path: Path) -> None:
    parsed = AnalysisService().analyze_file(tmp_path / "missing.py", "app/missing.py")

    assert parsed.path == "app/missing.py"
    assert parsed.parsed is False
    assert parsed.error is not None
    assert "could not be read" in parsed.error.message


def test_analyzing_a_missing_root_raises_instead_of_reporting_an_empty_repo(
    tmp_path: Path,
) -> None:
    service = AnalysisService()

    with pytest.raises(NotADirectoryError):
        service.analyze_repository(tmp_path / "missing-checkout")


def test_analysis_counts_summarize_analyzed_skipped_and_unparsed_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/main.py", "import os\n")
    _write(tmp_path, "app/broken.py", "def broken(:\n")
    _write(tmp_path, "README.md", "# Readme\n")

    counts = to_analysis_counts(AnalysisService().analyze_repository(tmp_path))

    assert (counts.analyzed, counts.excluded, counts.unparsed) == (2, 1, 1)

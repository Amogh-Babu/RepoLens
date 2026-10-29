"""Tests for vendored, generated, and oversized file exclusion (#26).

Every size here comes from the local fixture tree or from literal numbers, so
these tests make no network calls and never run repository code.
"""

from pathlib import Path

import pytest

from repolens.ingestion import (
    ArchiveLimits,
    FileTooLargeError,
    IngestionError,
    RepositoryTooLargeError,
    Snapshot,
    SourceFileFilter,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "filter_mini_repo"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _fixture_snapshot() -> Snapshot:
    """Describe the fixture tree as an extracted snapshot."""
    files = tuple(
        sorted(
            path.relative_to(FIXTURE_ROOT).as_posix()
            for path in FIXTURE_ROOT.rglob("*")
            if path.is_file()
        )
    )
    return Snapshot(
        repo="https://github.com/octocat/filter-mini-repo",
        sha=SHA,
        root=str(FIXTURE_ROOT),
        files=files,
    )


def test_the_repositorys_own_source_is_analyzed() -> None:
    file_filter = SourceFileFilter()

    assert file_filter.exclusion_for("app/main.py", 1_024) is None
    assert file_filter.should_analyze("app/services/billing.py")
    assert file_filter.should_analyze("README.md")
    assert file_filter.should_analyze("web/src/App.tsx")
    assert file_filter.should_analyze("requirements.txt")
    assert file_filter.should_analyze("app/migrations/0001_initial.py")


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/left-pad/index.js",
        "vendor/leftpad/leftpad.py",
        "app/vendored/pkg/module.py",
        "third_party/parser/parse.py",
        "thirdparty/parse.py",
        ".venv/lib/python3.13/site-packages/attrs/__init__.py",
        "web/bower_components/jquery/jquery.js",
        "ios/Pods/Alamofire/Source/Alamofire.swift",
    ],
)
def test_vendored_directories_are_excluded(path: str) -> None:
    exclusion = SourceFileFilter().exclusion_for(path)

    assert exclusion is not None
    assert exclusion.reason == "vendored"
    assert exclusion.path == path
    assert exclusion.message.startswith(f"{path}: ")


@pytest.mark.parametrize(
    "path",
    [
        ".git/hooks/pre-commit.py",
        "app/__pycache__/main.cpython-313.pyc",
        ".mypy_cache/3.13/app/main.json",
        ".tox/py313/log/commands.log",
    ],
)
def test_tool_and_version_control_directories_are_excluded(path: str) -> None:
    exclusion = SourceFileFilter().exclusion_for(path)

    assert exclusion is not None
    assert exclusion.reason == "metadata"


@pytest.mark.parametrize(
    "path",
    [
        "build/bundled_app.py",
        "dist/app-1.0.0/app/main.py",
        "target/debug/build/main.rs",
        "htmlcov/index.html",
        "app.egg-info/SOURCES.txt",
        "web/__generated__/schema.ts",
        "app/schema_pb2.py",
        "app/schema_pb2_grpc.py",
        "app/settings_generated.py",
        "app/schema.generated.py",
        "api/schema.pb.go",
        "static/app.min.js",
        "static/app.min.css",
        "static/app.js.map",
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "go.sum",
    ],
)
def test_generated_files_and_directories_are_excluded(path: str) -> None:
    exclusion = SourceFileFilter().exclusion_for(path)

    assert exclusion is not None
    assert exclusion.reason == "generated"


def test_directory_and_name_rules_ignore_case() -> None:
    file_filter = SourceFileFilter()

    assert file_filter.exclusion_for("Vendor/pkg/module.py") is not None
    assert file_filter.exclusion_for("app/Build/bundled.py") is not None
    assert file_filter.exclusion_for("Yarn.LOCK") is not None
    assert file_filter.exclusion_for("static/App.Min.JS") is not None


def test_windows_separators_cannot_hide_a_vendored_directory() -> None:
    exclusion = SourceFileFilter().exclusion_for("app\\node_modules\\dep\\index.js")

    assert exclusion is not None
    assert exclusion.reason == "vendored"


def test_a_directory_named_like_an_excluded_file_is_still_walked() -> None:
    file_filter = SourceFileFilter()

    assert file_filter.directory_exclusion_for("app/services") is None
    assert file_filter.directory_exclusion_for("docs") is None
    assert file_filter.directory_exclusion_for("") is None

    pruned = file_filter.directory_exclusion_for("web/node_modules")
    assert pruned is not None
    assert pruned.reason == "vendored"
    assert file_filter.directory_exclusion_for("app.egg-info") is not None


def test_a_file_over_the_per_file_cap_is_excluded() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_file_bytes=1_000))

    exclusion = file_filter.exclusion_for("app/data.py", 1_001)
    assert exclusion is not None
    assert exclusion.reason == "too_large"
    assert "1001 bytes" in exclusion.detail
    assert "1000 byte" in exclusion.detail

    assert file_filter.exclusion_for("app/data.py", 1_000) is None


def test_the_per_file_cap_is_skipped_when_the_size_is_unknown() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_file_bytes=1))

    assert file_filter.should_analyze("app/main.py")
    assert not file_filter.should_analyze("app/main.py", 2)


def test_callers_can_add_their_own_excluded_directories_and_suffixes() -> None:
    file_filter = SourceFileFilter(
        extra_excluded_directories=("generated_clients/",),
        extra_excluded_suffixes=(".pb.rs",),
    )

    assert file_filter.exclusion_for("generated_clients/api/client.py") is not None
    assert file_filter.exclusion_for("src/schema.pb.rs") is not None
    assert file_filter.exclusion_for("src/schema.rs") is None


def test_requiring_one_oversized_file_raises_a_structured_error() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_file_bytes=2_048))

    file_filter.require_file_within_limits("app/main.py", 2_048)

    with pytest.raises(FileTooLargeError) as error:
        file_filter.require_file_within_limits("app/data.py", 10_000)

    assert isinstance(error.value, IngestionError)
    assert error.value.status_code == 413
    assert error.value.to_dict() == {
        "code": "FILE_TOO_LARGE",
        "message": (
            "'app/data.py' is 10000 bytes, more than the 2048 byte per-file limit."
        ),
        "hint": "Large data and generated files are not analyzed.",
    }


def test_filter_files_reports_analyzable_files_and_every_exclusion() -> None:
    report = SourceFileFilter().filter_files(
        [
            ("app/main.py", 100),
            ("vendor/leftpad/leftpad.py", 200),
            ("app/helpers.py", 300),
            ("package-lock.json", 400),
        ]
    )

    assert report.analyzable_paths == ("app/main.py", "app/helpers.py")
    assert report.analyzable_count == 2
    assert report.analyzable_bytes == 400
    assert report.excluded_paths == ("vendor/leftpad/leftpad.py", "package-lock.json")
    assert report.excluded_count == 2

    vendored = report.exclusion_for("vendor/leftpad/leftpad.py")
    assert vendored is not None and vendored.reason == "vendored"
    assert report.exclusion_for("app/main.py") is None


def test_a_repository_over_the_source_byte_cap_is_rejected() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_analyzable_bytes=500))

    with pytest.raises(RepositoryTooLargeError) as error:
        file_filter.filter_files([("app/a.py", 400), ("app/b.py", 200)])

    assert error.value.status_code == 413
    assert error.value.to_dict() == {
        "code": "REPOSITORY_TOO_LARGE",
        "message": (
            "This repository holds more than 500 bytes of source to analyze, "
            "past the size limit."
        ),
        "hint": "Analyze a smaller repository.",
    }


def test_a_repository_over_the_source_file_count_cap_is_rejected() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_analyzable_file_count=2))

    with pytest.raises(RepositoryTooLargeError) as error:
        file_filter.filter_files(
            [("app/a.py", 1), ("app/b.py", 1), ("app/c.py", 1)]
        )

    assert error.value.code == "REPOSITORY_TOO_LARGE"
    assert "more than 2 source files" in error.value.message


def test_the_repository_caps_count_only_the_files_that_are_analyzed() -> None:
    file_filter = SourceFileFilter(
        ArchiveLimits(
            max_file_bytes=1_000,
            max_analyzable_bytes=1_000,
            max_analyzable_file_count=2,
        )
    )

    report = file_filter.filter_files(
        [
            ("app/main.py", 500),
            ("node_modules/dep/index.js", 10_000_000),
            ("app/data.json", 5_000),
            ("dist/app.py", 900),
            ("app/helpers.py", 400),
        ]
    )

    assert report.analyzable_paths == ("app/main.py", "app/helpers.py")
    assert report.analyzable_bytes == 900


def test_filtering_the_fixture_snapshot_keeps_only_its_own_source() -> None:
    report = SourceFileFilter().filter_snapshot(_fixture_snapshot())

    assert report.analyzable_paths == (
        "README.md",
        "app/__init__.py",
        "app/bulk_table.py",
        "app/helpers.py",
        "app/main.py",
        "docs/notes.md",
    )
    assert {
        exclusion.path: exclusion.reason for exclusion in report.exclusions
    } == {
        "app.egg-info/entry_points.py": "generated",
        "app/schema_pb2.py": "generated",
        "app/settings_generated.py": "generated",
        "build/bundled_app.py": "generated",
        "node_modules/left-pad/index.js": "vendored",
        "package-lock.json": "generated",
        "static/app.min.js": "generated",
        "third_party/parser/parse.py": "vendored",
        "vendor/leftpad/__init__.py": "vendored",
        "vendor/leftpad/leftpad.py": "vendored",
    }
    assert report.analyzable_bytes == sum(
        (FIXTURE_ROOT / path).stat().st_size for path in report.analyzable_paths
    )


def test_filtering_the_fixture_snapshot_applies_a_lowered_per_file_cap() -> None:
    file_filter = SourceFileFilter(ArchiveLimits(max_file_bytes=1_024))

    report = file_filter.filter_snapshot(_fixture_snapshot())

    oversized = report.exclusion_for("app/bulk_table.py")
    assert oversized is not None
    assert oversized.reason == "too_large"
    assert "app/bulk_table.py" not in report.analyzable_paths
    assert "app/main.py" in report.analyzable_paths


def test_filtering_a_snapshot_whose_files_are_gone_reports_what_is_left(
    tmp_path: Path,
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("import os\n", encoding="utf-8")
    snapshot = Snapshot(
        repo="https://github.com/octocat/hello-world",
        sha=SHA,
        root=str(tmp_path),
        files=("app/main.py", "app/deleted.py"),
    )

    report = SourceFileFilter().filter_snapshot(snapshot)

    assert report.analyzable_paths == ("app/main.py",)
    assert report.exclusions == ()


def test_the_filter_exposes_its_limits_and_the_file_filter_port() -> None:
    limits = ArchiveLimits(max_file_bytes=7)
    file_filter = SourceFileFilter(limits)

    assert file_filter.limits is limits
    assert callable(file_filter.exclusion_for)
    assert callable(file_filter.directory_exclusion_for)
    assert callable(file_filter.require_repository_within_limits)

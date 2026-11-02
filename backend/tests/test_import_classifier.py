"""Tests for classifying imports as internal, external, or unresolved."""

from repolens.analysis import classify_imports, to_analyzed_files
from repolens.graph import AnalyzedFile, ImportRecord

from analysis_fixture import analyze_fixture


def _imports_by_path(files: tuple[AnalyzedFile, ...]) -> dict[str, list[tuple]]:
    return {
        file.path: [
            (record.raw_name, record.kind, record.target_path or record.target_package)
            for record in file.imports
        ]
        for file in files
    }


def _classify(*files: AnalyzedFile) -> dict[str, list[tuple]]:
    return _imports_by_path(classify_imports(files))


def _imp(raw_name: str, level: int = 0, symbols: tuple[str, ...] = ()) -> ImportRecord:
    return ImportRecord(
        raw_name=raw_name, kind="unresolved", level=level, symbols=symbols
    )


def test_classifies_the_analysis_mini_repo() -> None:
    files = classify_imports(to_analyzed_files(analyze_fixture()))
    imports = _imports_by_path(files)

    assert imports["app/main.py"] == [
        ("argparse", "external", "argparse"),
        ("os.path", "external", "os"),
        ("app.config", "internal", "app/config.py"),
        ("app.services.billing", "internal", "app/services/billing.py"),
    ]
    assert imports["app/__init__.py"] == [
        (".config", "internal", "app/config.py"),
        (".services", "internal", "app/services/__init__.py"),
    ]
    assert imports["app/services/billing.py"] == [
        ("decimal", "external", "decimal"),
        ("..config", "internal", "app/config.py"),
    ]
    assert ("ujson", "external", "ujson") in imports["app/compat.py"]
    assert ("app.config", "internal", "app/config.py") in imports["app/compat.py"]


def test_from_import_of_submodules_yields_one_record_per_module() -> None:
    imports = _classify(
        AnalyzedFile(
            path="main.py",
            imports=(_imp("pkg", symbols=("alpha", "beta", "helper")),),
        ),
        AnalyzedFile(path="pkg/__init__.py"),
        AnalyzedFile(path="pkg/alpha.py"),
        AnalyzedFile(path="pkg/beta.py"),
    )

    assert imports["main.py"] == [
        ("pkg", "internal", "pkg/__init__.py"),
        ("pkg.alpha", "internal", "pkg/alpha.py"),
        ("pkg.beta", "internal", "pkg/beta.py"),
    ]


def test_from_import_of_only_submodules_skips_the_package_itself() -> None:
    imports = _classify(
        AnalyzedFile(path="main.py", imports=(_imp("pkg", symbols=("alpha",)),)),
        AnalyzedFile(path="pkg/__init__.py"),
        AnalyzedFile(path="pkg/alpha.py"),
    )

    assert imports["main.py"] == [("pkg.alpha", "internal", "pkg/alpha.py")]


def test_resolves_absolute_imports_under_a_src_layout() -> None:
    imports = _classify(
        AnalyzedFile(path="tests/test_core.py", imports=(_imp("lib.core"),)),
        AnalyzedFile(path="src/lib/__init__.py"),
        AnalyzedFile(path="src/lib/core.py"),
    )

    assert imports["tests/test_core.py"] == [
        ("lib.core", "internal", "src/lib/core.py")
    ]


def test_falls_back_to_the_closest_parent_package() -> None:
    imports = _classify(
        AnalyzedFile(path="main.py", imports=(_imp("pkg.generated.models"),)),
        AnalyzedFile(path="pkg/__init__.py"),
    )

    assert imports["main.py"] == [
        ("pkg.generated.models", "internal", "pkg/__init__.py")
    ]


def test_missing_local_and_relative_targets_are_unresolved() -> None:
    imports = _classify(
        AnalyzedFile(
            path="pkg/mod.py",
            imports=(
                _imp(".missing", level=1),
                _imp("....too_high", level=4),
            ),
        ),
        AnalyzedFile(path="pkg/__init__.py"),
    )

    assert imports["pkg/mod.py"] == [
        (".missing", "unresolved", None),
        ("....too_high", "unresolved", None),
    ]


def test_star_import_links_to_the_package_and_self_imports_are_dropped() -> None:
    imports = _classify(
        AnalyzedFile(
            path="pkg/__init__.py",
            imports=(_imp(".", level=1, symbols=("helper",)), _imp(".sub", 1, ("*",))),
        ),
        AnalyzedFile(path="pkg/sub.py"),
    )

    assert imports["pkg/__init__.py"] == [
        (".", "unresolved", None),
        (".sub", "internal", "pkg/sub.py"),
    ]


def test_prefers_a_module_over_its_type_stub() -> None:
    imports = _classify(
        AnalyzedFile(path="main.py", imports=(_imp("util"),)),
        AnalyzedFile(path="util.pyi"),
        AnalyzedFile(path="util.py"),
    )

    assert imports["main.py"] == [("util", "internal", "util.py")]

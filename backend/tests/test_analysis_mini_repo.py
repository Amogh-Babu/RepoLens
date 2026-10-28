"""Analysis of the mini repository fixture tree (#22).

The fixture's Python files are read and parsed; they are never imported or
executed. Update the expectations below when the fixture source changes.
"""

import sys

from repolens.analysis import AnalysisService

from analysis_fixture import FIXTURE_ROOT, analyze_fixture


EXPECTED_IMPORTS: dict[str, list[str]] = {
    "app/__init__.py": [".", ".services"],
    "app/compat.py": ["sys", "typing", "app.config", "ujson", "json"],
    "app/config.py": ["dataclasses"],
    "app/main.py": [
        "argparse",
        "os.path",
        "app.config",
        "app.services.billing",
        "app.services",
    ],
    "app/services/__init__.py": [".billing"],
    "app/services/billing.py": ["decimal", "..", "..config"],
    "app/services/broken.py": [],
}

EXPECTED_SYMBOLS: dict[str, list[tuple[str, str]]] = {
    "app/__init__.py": [],
    "app/compat.py": [
        ("SettingsLike", "class"),
        ("LEGACY_JSON", "variable"),
        ("DEFAULT_ENCODING", "variable"),
        ("cache_directory", "function"),
        ("JsonCodec", "class"),
        ("load_settings", "function"),
    ],
    "app/config.py": [
        ("DEFAULT_TIMEOUT", "variable"),
        ("RETRY_LIMIT", "variable"),
        ("BACKOFF_SECONDS", "variable"),
        ("Settings", "class"),
    ],
    "app/main.py": [
        ("VERSION", "variable"),
        ("DEBUG", "variable"),
        ("build_parser", "function"),
        ("run", "function"),
        ("main", "function"),
    ],
    "app/services/__init__.py": [("__all__", "variable")],
    "app/services/billing.py": [
        ("TAX_RATES", "variable"),
        ("InvoiceCalculator", "class"),
        ("default_calculator", "function"),
    ],
    "app/services/broken.py": [],
}


def test_every_python_file_in_the_fixture_is_analyzed() -> None:
    analysis = analyze_fixture()
    source_paths = {
        path.relative_to(FIXTURE_ROOT).as_posix() for path in FIXTURE_ROOT.rglob("*.py")
    }

    assert {parsed.path for parsed in analysis.files} == source_paths
    assert analysis.skipped_paths == ("README.md", "notes.md")
    assert {parsed.language for parsed in analysis.files} == {"python"}


def test_imports_are_reported_per_file() -> None:
    analysis = analyze_fixture()

    assert {
        parsed.path: [imported.raw_name for imported in parsed.imports]
        for parsed in analysis.files
    } == EXPECTED_IMPORTS


def test_top_level_symbols_are_reported_per_file() -> None:
    analysis = analyze_fixture()

    assert {
        parsed.path: [(symbol.name, symbol.kind) for symbol in parsed.symbols]
        for parsed in analysis.files
    } == EXPECTED_SYMBOLS


def test_relative_imports_keep_the_depth_the_resolver_needs() -> None:
    billing = analyze_fixture().get("app/services/billing.py")
    assert billing is not None

    relative = {
        imported.raw_name: (imported.level, imported.module, imported.symbols)
        for imported in billing.imports
        if imported.is_relative
    }

    assert relative == {
        "..": (2, None, ("config",)),
        "..config": (2, "config", ("DEFAULT_TIMEOUT",)),
    }


def test_conditional_module_level_declarations_are_reported() -> None:
    compat = analyze_fixture().get("app/compat.py")
    assert compat is not None

    # The optional-dependency fallback: both branches' modules are reported.
    json_imports = [
        imported.raw_name
        for imported in compat.imports
        if "json" in imported.raw_name
    ]
    assert json_imports == ["ujson", "json"]
    # The typing-only import, merged with the same module imported in a function.
    type_checking_import = next(
        imported for imported in compat.imports if imported.raw_name == "app.config"
    )
    assert type_checking_import.symbols == ("Settings",)
    assert type_checking_import.line == 7

    declared = {symbol.name: symbol.kind for symbol in compat.symbols}
    assert declared["SettingsLike"] == "class"  # declared under if TYPE_CHECKING
    assert declared["LEGACY_JSON"] == "variable"  # declared in an except handler
    assert declared["DEFAULT_ENCODING"] == "variable"  # version-gated assignment
    assert declared["cache_directory"] == "function"  # defined in both branches
    assert "encode" not in declared  # a method, not a module-level symbol


def test_the_unparsable_file_does_not_hide_the_rest_of_the_repository() -> None:
    analysis = analyze_fixture()
    broken = analysis.get("app/services/broken.py")
    assert broken is not None

    assert broken.parsed is False
    assert broken.error is not None
    assert broken.error.line == 3
    assert analysis.unparsed_count == 1
    assert analysis.parsed_count == len(analysis.files) - 1


def test_analyzing_the_fixture_does_not_import_its_modules() -> None:
    analyze_fixture()

    assert "app.services.billing" not in sys.modules
    assert str(FIXTURE_ROOT) not in sys.path


def test_the_search_fixture_repository_also_parses_into_imports_and_symbols() -> None:
    search_repo_root = FIXTURE_ROOT.parent / "search_mini_repo"

    analysis = AnalysisService().analyze_repository(search_repo_root)

    assert analysis.unparsed_count == 0
    assert {parsed.path for parsed in analysis.files} == {
        path.relative_to(search_repo_root).as_posix()
        for path in search_repo_root.rglob("*.py")
    }

    routes = analysis.get("app/authentication/routes.py")
    assert routes is not None
    assert [imported.raw_name for imported in routes.imports] == [
        "app.authentication.service",
        "app.users.repository",
    ]
    assert [(symbol.name, symbol.kind) for symbol in routes.symbols] == [
        ("post_login", "function"),
    ]

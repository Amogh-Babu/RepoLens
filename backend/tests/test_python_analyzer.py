"""Unit tests for the ast-based Python LanguageAnalyzer (#22)."""

import textwrap

from repolens.analysis import (
    LanguageAnalyzer,
    ParsedImport,
    ParsedSymbol,
    PythonAnalyzer,
)


def _analyze(source: str, path: str = "pkg/module.py"):
    return PythonAnalyzer().analyze(path, textwrap.dedent(source).lstrip("\n"))


def _imports(source: str) -> list[tuple[str, str, int, tuple[str, ...]]]:
    return [
        (imported.raw_name, imported.form, imported.level, imported.symbols)
        for imported in _analyze(source).imports
    ]


def _symbols(source: str) -> list[tuple[str, str, int]]:
    return [
        (symbol.name, symbol.kind, symbol.line) for symbol in _analyze(source).symbols
    ]


def test_python_analyzer_satisfies_the_language_analyzer_interface() -> None:
    analyzer = PythonAnalyzer()

    assert isinstance(analyzer, LanguageAnalyzer)
    assert analyzer.language == "python"
    assert analyzer.supports("app/main.py")
    assert analyzer.supports("app/types.pyi")
    assert analyzer.supports("APP/MAIN.PY")
    assert not analyzer.supports("app/main.ts")
    assert not analyzer.supports("README.md")
    assert not analyzer.supports("pyproject.toml")


def test_plain_imports_report_dotted_module_names() -> None:
    assert _imports(
        """
        import os
        import os.path
        import numpy as np
        import json, csv
        """
    ) == [
        ("os", "import", 0, ()),
        ("os.path", "import", 0, ()),
        ("numpy", "import", 0, ()),
        ("csv", "import", 0, ()),
        ("json", "import", 0, ()),
    ]


def test_from_imports_report_the_module_and_the_imported_names() -> None:
    assert _imports(
        """
        from app.config import DEFAULT_TIMEOUT, Settings
        from app.services import billing as billing_service
        from collections.abc import Iterable
        """
    ) == [
        ("app.config", "from", 0, ("DEFAULT_TIMEOUT", "Settings")),
        ("app.services", "from", 0, ("billing",)),
        ("collections.abc", "from", 0, ("Iterable",)),
    ]


def test_relative_imports_keep_their_depth_and_dotted_name() -> None:
    parsed = _analyze(
        """
        from . import config
        from .billing import InvoiceCalculator
        from .. import shared
        from ..config import DEFAULT_TIMEOUT
        from ...app.services import billing
        """
    )

    assert [
        (imported.raw_name, imported.level, imported.module, imported.is_relative)
        for imported in parsed.imports
    ] == [
        (".", 1, None, True),
        (".billing", 1, "billing", True),
        ("..", 2, None, True),
        ("..config", 2, "config", True),
        ("...app.services", 3, "app.services", True),
    ]


def test_star_import_reports_the_star_as_the_imported_name() -> None:
    assert _imports("from app.services import *") == [
        ("app.services", "from", 0, ("*",)),
    ]


def test_imports_inside_functions_and_classes_are_reported() -> None:
    assert _imports(
        """
        def run() -> None:
            import heapq

            from app.services import billing

            class Local:
                import csv
        """
    ) == [
        ("heapq", "import", 0, ()),
        ("app.services", "from", 0, ("billing",)),
        ("csv", "import", 0, ()),
    ]


def test_repeated_imports_of_one_module_merge_into_a_single_record() -> None:
    parsed = _analyze(
        """
        from app.config import Settings
        import app.config

        def reload() -> None:
            from app.config import DEFAULT_TIMEOUT, Settings
        """
    )

    assert parsed.imports == (
        ParsedImport(
            module="app.config",
            form="from",
            level=0,
            symbols=("Settings", "DEFAULT_TIMEOUT"),
            line=1,
        ),
        ParsedImport(module="app.config", form="import", level=0, line=2),
    )


def test_a_file_without_imports_reports_no_imports() -> None:
    parsed = _analyze(
        """
        \"\"\"Module docstring only.\"\"\"

        VALUE = 1
        """
    )

    assert parsed.imports == ()
    assert parsed.parsed is True


def test_top_level_functions_classes_and_variables_are_reported() -> None:
    assert _symbols(
        """
        \"\"\"Module docstring.\"\"\"

        import os

        VERSION = "1.0.0"
        DEBUG: bool = False
        RETRY_LIMIT, BACKOFF_SECONDS = 3, 1.5


        class Settings:
            \"\"\"Settings.\"\"\"

            tax_rate: float = 0.1


        def build() -> None:
            \"\"\"Build.\"\"\"


        async def run() -> None:
            \"\"\"Run.\"\"\"
        """
    ) == [
        ("VERSION", "variable", 5),
        ("DEBUG", "variable", 6),
        ("RETRY_LIMIT", "variable", 7),
        ("BACKOFF_SECONDS", "variable", 7),
        ("Settings", "class", 10),
        ("build", "function", 16),
        ("run", "function", 20),
    ]


def test_decorated_definitions_report_the_definition_line() -> None:
    assert _symbols(
        """
        import functools


        @functools.cache
        def cached() -> int:
            return 1
        """
    ) == [("cached", "function", 5)]


def test_methods_and_nested_definitions_are_not_top_level_symbols() -> None:
    assert _symbols(
        """
        class Calculator:
            rate = 0.1

            def total(self) -> float:
                inner = 1.0

                def helper() -> float:
                    return inner

                return helper()


        def outer() -> None:
            class Local:
                pass
        """
    ) == [("Calculator", "class", 1), ("outer", "function", 13)]


def test_optional_dependency_imports_report_both_branches() -> None:
    parsed = _analyze(
        """
        try:
            import ujson as json_backend
        except ImportError:
            import json as json_backend

            LEGACY_JSON = True
        """
    )

    assert [imported.raw_name for imported in parsed.imports] == ["ujson", "json"]
    assert [(symbol.name, symbol.kind, symbol.line) for symbol in parsed.symbols] == [
        ("LEGACY_JSON", "variable", 6),
    ]


def test_type_checking_imports_and_declarations_are_reported() -> None:
    parsed = _analyze(
        """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from app.config import Settings

            class SettingsLike:
                tax_rate: float
        """
    )

    assert [imported.raw_name for imported in parsed.imports] == [
        "typing",
        "app.config",
    ]
    assert [(symbol.name, symbol.kind, symbol.line) for symbol in parsed.symbols] == [
        ("SettingsLike", "class", 6),
    ]


def test_declarations_guarded_by_module_level_control_flow_are_reported() -> None:
    assert _symbols(
        """
        import sys

        if sys.version_info >= (3, 12):
            ENCODING = "utf-8"
        else:
            ENCODING = "utf8"

        try:
            RATE = 0.1
        except ValueError:
            RATE = 0.0
        finally:
            CHECKED = True

        for _name in ("a",):
            LAST_NAME = _name

        while False:
            UNREACHABLE = True

        with open("mini.toml") as handle:
            class Config:
                pass

        match sys.platform:
            case "linux":
                PLATFORM = "linux"
            case _:
                PLATFORM = "other"
        """
    ) == [
        ("ENCODING", "variable", 4),
        ("RATE", "variable", 9),
        ("CHECKED", "variable", 13),
        ("LAST_NAME", "variable", 16),
        ("UNREACHABLE", "variable", 19),
        ("Config", "class", 22),
        ("PLATFORM", "variable", 27),
    ]


def test_a_conditional_definition_is_reported_once_at_its_first_branch() -> None:
    assert _symbols(
        """
        import sys

        if sys.platform == "win32":

            def cache_directory() -> str:
                return "C:/Users/mini/cache"

        else:

            def cache_directory() -> str:
                return "/var/cache/mini"
        """
    ) == [("cache_directory", "function", 5)]


def test_control_flow_traversal_still_stops_at_function_and_class_scopes() -> None:
    assert _symbols(
        """
        import sys

        if sys.platform == "linux":

            def configure() -> None:
                TIMEOUT = 30

                if TIMEOUT:
                    RETRIES = 2

            class Runner:
                if sys.platform == "linux":
                    attribute = 1
        """
    ) == [("configure", "function", 5), ("Runner", "class", 11)]


def test_attribute_and_subscript_assignments_declare_no_symbol() -> None:
    assert _symbols(
        """
        import logging

        logging.basicConfig()
        logging.root.level = 10
        TABLE = {}
        TABLE["key"] = "value"
        alias = other = 2
        """
    ) == [
        ("TABLE", "variable", 5),
        ("alias", "variable", 7),
        ("other", "variable", 7),
    ]


def test_a_symbol_assigned_twice_is_reported_once_at_its_first_line() -> None:
    assert _symbols(
        """
        TIMEOUT = 1
        TIMEOUT = 2
        """
    ) == [("TIMEOUT", "variable", 1)]


def test_syntax_errors_are_reported_instead_of_raised() -> None:
    parsed = _analyze(
        """
        import os

        def broken(:
            return 1
        """,
        path="app/broken.py",
    )

    assert parsed.path == "app/broken.py"
    assert parsed.language == "python"
    assert parsed.parsed is False
    assert parsed.imports == ()
    assert parsed.symbols == ()
    assert parsed.error is not None
    assert parsed.error.message
    assert parsed.error.line == 3
    assert parsed.line_count == 4


def test_source_with_a_null_byte_is_reported_as_unparsed() -> None:
    parsed = PythonAnalyzer().analyze("app/nul.py", "VALUE = 1\x00\n")

    assert parsed.parsed is False
    assert parsed.error is not None
    assert parsed.error.message


def test_line_count_counts_source_lines() -> None:
    assert _analyze("import os\nimport csv\n").line_count == 2
    assert PythonAnalyzer().analyze("empty.py", "").line_count == 0


def test_parsed_symbol_and_import_records_are_immutable_values() -> None:
    assert ParsedSymbol(name="run", kind="function", line=3) == ParsedSymbol(
        name="run", kind="function", line=3
    )
    assert ParsedImport(module="os", line=1).raw_name == "os"
    assert ParsedImport(module=None, level=1, form="from").raw_name == "."

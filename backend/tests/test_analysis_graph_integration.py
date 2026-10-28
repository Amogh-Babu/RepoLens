"""Analysis results flow into the graph store and search (#22).

Import classification is not part of this step, so every import is stored as
`unresolved` until the import classifier assigns internal or external kinds.
"""

import time

from repolens.analysis import (
    to_analysis_counts,
    to_analyzed_file,
    to_analyzed_files,
)
from repolens.graph import AnalysisRecord, SqliteGraphStore
from repolens.search import SearchService

from analysis_fixture import analyze_fixture


def _saved_store() -> SqliteGraphStore:
    analysis = analyze_fixture()
    store = SqliteGraphStore()
    store.save(
        AnalysisRecord(
            analysis_id="analysis-1",
            repo="https://github.com/octocat/mini-repo",
            sha="0123456789abcdef0123456789abcdef01234567",
            created_at=time.time(),
            counts=to_analysis_counts(analysis),
            files=to_analyzed_files(analysis),
        )
    )
    return store


def test_parsed_files_convert_to_storable_analyzed_files() -> None:
    analysis = analyze_fixture()
    config = analysis.get("app/config.py")
    assert config is not None

    analyzed = to_analyzed_file(config)

    assert analyzed.path == "app/config.py"
    assert analyzed.parsed is True
    assert analyzed.line_count == config.line_count
    assert analyzed.module == ""
    assert [(symbol.name, symbol.kind, symbol.line) for symbol in analyzed.symbols] == [
        ("DEFAULT_TIMEOUT", "variable", 5),
        ("RETRY_LIMIT", "variable", 6),
        ("BACKOFF_SECONDS", "variable", 6),
        ("Settings", "class", 10),
    ]
    assert [(imported.raw_name, imported.kind) for imported in analyzed.imports] == [
        ("dataclasses", "unresolved"),
    ]


def test_the_graph_store_groups_analyzed_files_into_modules() -> None:
    graph = _saved_store().get_graph("analysis-1")

    assert [node.path for node in graph.files] == [
        "app/__init__.py",
        "app/compat.py",
        "app/config.py",
        "app/main.py",
        "app/services/__init__.py",
        "app/services/billing.py",
        "app/services/broken.py",
    ]
    assert [(group.id, group.name) for group in graph.modules] == [
        ("app", "app"),
        ("app/services", "services"),
    ]
    # Edges need resolved internal imports, which the classifier adds later.
    assert graph.edges == ()


def test_file_detail_exposes_symbols_and_unresolved_imports() -> None:
    detail = _saved_store().get_file("analysis-1", "app/main.py")

    assert [symbol.name for symbol in detail.symbols] == [
        "VERSION",
        "DEBUG",
        "build_parser",
        "run",
        "main",
    ]
    assert detail.symbols[0].source_url.endswith("/app/main.py#L9")
    assert detail.module == "app"
    assert detail.unresolved_imports == (
        "argparse",
        "os.path",
        "app.config",
        "app.services.billing",
        "app.services",
    )
    assert detail.internal_imports == ()
    assert detail.external_imports == ()


def test_the_unparsed_file_is_stored_and_counted() -> None:
    store = _saved_store()

    broken = store.get_file("analysis-1", "app/services/broken.py")
    assert broken.parsed is False
    assert broken.symbols == ()
    assert broken.imports == ()

    summary = store.get_summary("analysis-1")
    assert summary["counts"] == {"analyzed": 7, "excluded": 2, "unparsed": 1}


def test_search_finds_analyzed_files_by_symbol_and_import_name() -> None:
    service = SearchService(_saved_store())

    by_symbol = service.search("analysis-1", "InvoiceCalculator")
    assert "app/services/billing.py" in [result.path for result in by_symbol.results]

    by_import = service.search("analysis-1", "dataclasses")
    assert [result.path for result in by_import.results] == ["app/config.py"]

"""Import resolution and internal/external classification (#27).

The mini repository fixture is read and parsed, never imported or executed.
Classification runs on the storable records the analysis adapter produces, so
these tests go through `to_analyzed_files` the way the pipeline does.
"""

import time
from pathlib import Path

from repolens.analysis import (
    AnalysisService,
    ImportClassifier,
    classify_imports,
    to_analysis_counts,
    to_analyzed_files,
)
from repolens.graph import AnalysisRecord, AnalyzedFile, ImportRecord, SqliteGraphStore

from analysis_fixture import analyze_fixture


def _classified_fixture() -> dict[str, AnalyzedFile]:
    """Classify every import in the mini repository fixture, keyed by path."""
    files = classify_imports(to_analyzed_files(analyze_fixture()))
    return {file.path: file for file in files}


def _imports(file: AnalyzedFile) -> list[tuple[str, str, str | None]]:
    """Describe a file's imports as (raw_name, kind, target path or package)."""
    return [
        (
            imported.raw_name,
            imported.kind,
            imported.target_path or imported.target_package,
        )
        for imported in file.imports
    ]


def _unresolved() -> ImportClassifier:
    """Return a classifier for a repository with no files to resolve against."""
    return ImportClassifier(())


def test_a_sibling_relative_import_resolves_to_the_sibling_module() -> None:
    """`from . import config` in `app/__init__.py` is `app/config.py`."""
    classified = _classified_fixture()

    assert _imports(classified["app/__init__.py"])[0] == (
        ".",
        "internal",
        "app/config.py",
    )


def test_a_parent_relative_import_resolves_one_package_up() -> None:
    """`from .. import config` in `app/services/billing.py` is `app/config.py`."""
    classified = _classified_fixture()

    assert _imports(classified["app/services/billing.py"]) == [
        ("decimal", "external", "decimal"),
        ("..", "internal", "app/config.py"),
        ("..config", "internal", "app/config.py"),
    ]


def test_a_relative_import_of_a_submodule_resolves_to_that_file() -> None:
    classified = _classified_fixture()

    assert _imports(classified["app/services/__init__.py"]) == [
        (".billing", "internal", "app/services/billing.py"),
    ]


def test_an_absolute_import_of_a_repository_module_is_internal() -> None:
    """A trailing imported name is an attribute, not a submodule.

    `from app.config import DEFAULT_TIMEOUT, Settings` resolves to
    `app/config.py`; neither name is a module.
    """
    classified = _classified_fixture()

    assert _imports(classified["app/main.py"]) == [
        ("argparse", "external", "argparse"),
        ("os.path", "external", "os"),
        ("app.config", "internal", "app/config.py"),
        ("app.services.billing", "internal", "app/services/billing.py"),
        ("app.services", "internal", "app/services/billing.py"),
    ]


def test_a_single_name_that_is_a_submodule_resolves_to_the_submodule_file() -> None:
    """`from app.services import billing` points at the submodule file.

    The name could also be a re-export from `app/services/__init__.py`. The
    submodule wins, because an edge to the file that defines the code is more
    useful than an edge to the package that forwards it.
    """
    classifier = ImportClassifier(
        ("app/services/__init__.py", "app/services/billing.py")
    )

    resolved = classifier.classify(
        "app/main.py",
        ImportRecord(raw_name="app.services", kind="unresolved", symbols=("billing",)),
    )

    assert (resolved.kind, resolved.target_path) == (
        "internal",
        "app/services/billing.py",
    )


def test_several_imported_names_resolve_to_the_package_they_come_from() -> None:
    """One record holds one target, so a mixed name list targets the package."""
    classifier = ImportClassifier(
        (
            "app/services/__init__.py",
            "app/services/billing.py",
            "app/main.py",
        )
    )

    resolved = classifier.classify(
        "app/main.py",
        ImportRecord(
            raw_name="app.services",
            kind="unresolved",
            symbols=("billing", "InvoiceCalculator"),
        ),
    )

    assert (resolved.kind, resolved.target_path) == (
        "internal",
        "app/services/__init__.py",
    )


def test_a_star_import_is_resolved_from_its_module_not_its_names() -> None:
    """`from .services import *` names its module, so the target is known.

    Only the imported names are unknowable, and `'*'` is never resolved as a
    submodule.
    """
    classified = _classified_fixture()

    assert _imports(classified["app/__init__.py"])[1] == (
        ".services",
        "internal",
        "app/services/__init__.py",
    )


def test_a_star_import_of_an_external_package_is_external() -> None:
    resolved = _unresolved().classify(
        "app/main.py",
        ImportRecord(raw_name="numpy", kind="unresolved", symbols=("*",)),
    )

    assert (resolved.kind, resolved.target_package) == ("external", "numpy")


def test_a_star_import_of_a_missing_repository_module_stays_unresolved() -> None:
    """A star import is resolved from its module, and never guessed."""
    classifier = ImportClassifier(("app/__init__.py", "app/main.py"))

    resolved = classifier.classify(
        "app/main.py",
        ImportRecord(raw_name="app.plugins", kind="unresolved", symbols=("*",)),
    )

    assert (resolved.kind, resolved.target_path, resolved.target_package) == (
        "unresolved",
        None,
        None,
    )


def test_stdlib_and_third_party_imports_are_external_with_their_package() -> None:
    classified = _classified_fixture()

    assert _imports(classified["app/compat.py"]) == [
        ("sys", "external", "sys"),
        ("typing", "external", "typing"),
        ("app.config", "internal", "app/config.py"),
        ("ujson", "external", "ujson"),
        ("json", "external", "json"),
    ]
    assert _imports(classified["app/config.py"]) == [
        ("dataclasses", "external", "dataclasses"),
    ]


def test_an_external_package_keeps_its_top_level_name_only() -> None:
    resolved = _unresolved().classify(
        "app/main.py",
        ImportRecord(raw_name="urllib3.util.retry", kind="unresolved"),
    )

    assert (resolved.kind, resolved.target_package, resolved.target_path) == (
        "external",
        "urllib3",
        None,
    )


def test_every_fixture_import_is_labeled_internal_or_external() -> None:
    classified = _classified_fixture()

    kinds = {
        imported.kind for file in classified.values() for imported in file.imports
    }
    assert kinds == {"internal", "external"}


def test_a_package_directory_takes_precedence_over_a_same_named_module() -> None:
    classifier = ImportClassifier(("app/config.py", "app/config/__init__.py"))

    resolved = classifier.classify(
        "app/main.py", ImportRecord(raw_name="app.config", kind="unresolved")
    )

    assert resolved.target_path == "app/config/__init__.py"


def test_a_stub_only_module_resolves_to_its_pyi_file() -> None:
    classifier = ImportClassifier(("app/main.py", "app/protocol.pyi"))

    resolved = classifier.classify(
        "app/main.py", ImportRecord(raw_name="app.protocol", kind="unresolved")
    )

    assert (resolved.kind, resolved.target_path) == ("internal", "app/protocol.pyi")


def test_a_namespace_package_submodule_resolves_without_an_init_file() -> None:
    classifier = ImportClassifier(("app/__init__.py", "app/plugins/export.py"))

    resolved = classifier.classify(
        "app/main.py", ImportRecord(raw_name="app.plugins.export", kind="unresolved")
    )

    assert (resolved.kind, resolved.target_path) == (
        "internal",
        "app/plugins/export.py",
    )


def test_a_package_under_a_source_root_resolves_from_inside_that_root() -> None:
    """A `src/` layout imports `app.config`, not `src.app.config`."""
    classifier = ImportClassifier(
        ("src/app/__init__.py", "src/app/config.py", "src/app/main.py")
    )

    resolved = classifier.classify(
        "src/app/main.py",
        ImportRecord(raw_name="app.config", kind="unresolved", symbols=("Settings",)),
    )

    assert (resolved.kind, resolved.target_path) == ("internal", "src/app/config.py")
    assert classifier.source_roots == ("", "src")


def test_the_source_root_holding_the_importing_file_wins() -> None:
    """Two checkouts of one package resolve against the importer's own tree."""
    classifier = ImportClassifier(
        (
            "service_a/app/__init__.py",
            "service_a/app/config.py",
            "service_b/app/__init__.py",
            "service_b/app/config.py",
            "service_b/app/main.py",
        )
    )

    resolved = classifier.classify(
        "service_b/app/main.py",
        ImportRecord(raw_name="app.config", kind="unresolved"),
    )

    assert resolved.target_path == "service_b/app/config.py"


def test_a_missing_module_under_a_repository_package_stays_unresolved() -> None:
    """A broken repository-relative import is not an external package."""
    classifier = ImportClassifier(("app/__init__.py", "app/main.py"))

    resolved = classifier.classify(
        "app/main.py", ImportRecord(raw_name="app.missing", kind="unresolved")
    )

    assert (resolved.kind, resolved.target_path, resolved.target_package) == (
        "unresolved",
        None,
        None,
    )


def test_a_relative_import_reaching_past_the_repository_root_is_unresolved() -> None:
    classifier = ImportClassifier(("app/__init__.py", "app/main.py"))

    resolved = classifier.classify(
        "app/main.py",
        ImportRecord(
            raw_name="...config", kind="unresolved", level=3, symbols=("config",)
        ),
    )

    assert (resolved.kind, resolved.target_path, resolved.target_package) == (
        "unresolved",
        None,
        None,
    )


def test_a_relative_import_is_never_classified_as_an_external_package() -> None:
    resolved = _unresolved().classify(
        "app/main.py",
        ImportRecord(raw_name=".config", kind="unresolved", level=1),
    )

    assert (resolved.kind, resolved.target_package) == ("unresolved", None)


def test_a_package_import_of_an_unknown_name_does_not_target_its_own_file() -> None:
    """`from . import missing` in a package must not become a self edge."""
    classifier = ImportClassifier(("app/__init__.py",))

    resolved = classifier.classify(
        "app/__init__.py",
        ImportRecord(
            raw_name=".", kind="unresolved", level=1, symbols=("missing",)
        ),
    )

    assert (resolved.kind, resolved.target_path) == ("unresolved", None)


def test_classification_keeps_every_other_field_of_a_file_unchanged() -> None:
    analyzed = to_analyzed_files(analyze_fixture())

    classified = classify_imports(analyzed)

    assert [file.path for file in classified] == [file.path for file in analyzed]
    assert [file.symbols for file in classified] == [file.symbols for file in analyzed]
    assert [file.line_count for file in classified] == [
        file.line_count for file in analyzed
    ]
    assert [file.parsed for file in classified] == [file.parsed for file in analyzed]


def test_an_unparsable_file_is_classified_without_stopping_the_run() -> None:
    """The syntax-error fixture file has no imports and no target."""
    classified = _classified_fixture()
    broken = classified["app/services/broken.py"]

    assert broken.parsed is False
    assert broken.imports == ()
    assert len(classified) == 7


def test_an_unparsable_file_is_still_a_resolvable_import_target() -> None:
    """A file that did not parse is a repository file all the same."""
    classifier = ImportClassifier(
        ("app/services/__init__.py", "app/services/broken.py")
    )

    resolved = classifier.classify(
        "app/services/__init__.py",
        ImportRecord(
            raw_name=".", kind="unresolved", level=1, symbols=("broken",)
        ),
    )

    assert (resolved.kind, resolved.target_path) == (
        "internal",
        "app/services/broken.py",
    )


def _saved_store() -> SqliteGraphStore:
    """Save the classified fixture analysis the way the pipeline does."""
    analysis = analyze_fixture()
    store = SqliteGraphStore()
    store.save(
        AnalysisRecord(
            analysis_id="analysis-1",
            repo="https://github.com/octocat/mini-repo",
            sha="0123456789abcdef0123456789abcdef01234567",
            created_at=time.time(),
            counts=to_analysis_counts(analysis),
            files=classify_imports(to_analyzed_files(analysis)),
        )
    )
    return store


def test_classified_internal_imports_become_dependency_graph_edges() -> None:
    graph = _saved_store().get_graph("analysis-1")

    assert sorted({(edge.source, edge.target) for edge in graph.edges}) == [
        ("app/__init__.py", "app/config.py"),
        ("app/__init__.py", "app/services/__init__.py"),
        ("app/compat.py", "app/config.py"),
        ("app/main.py", "app/config.py"),
        ("app/main.py", "app/services/billing.py"),
        ("app/services/__init__.py", "app/services/billing.py"),
        ("app/services/billing.py", "app/config.py"),
    ]


def test_file_detail_splits_internal_and_external_imports() -> None:
    detail = _saved_store().get_file("analysis-1", "app/main.py")

    assert [
        (imported.raw_name, imported.target_path)
        for imported in detail.internal_imports
    ] == [
        ("app.config", "app/config.py"),
        ("app.services.billing", "app/services/billing.py"),
        ("app.services", "app/services/billing.py"),
    ]
    assert [
        (imported.raw_name, imported.package) for imported in detail.external_imports
    ] == [("argparse", "argparse"), ("os.path", "os")]
    assert detail.unresolved_imports == ()


def test_the_unparsable_file_survives_classification_and_storage() -> None:
    store = _saved_store()

    broken = store.get_file("analysis-1", "app/services/broken.py")
    assert broken.parsed is False
    assert broken.imports == ()

    summary = store.get_summary("analysis-1")
    assert summary["counts"] == {"analyzed": 7, "excluded": 2, "unparsed": 1}


def test_a_repository_with_a_broken_package_init_still_classifies(
    tmp_path: Path,
) -> None:
    """One unparsable file cannot stop resolution for the files around it."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("def broken(\n", encoding="utf-8")
    (tmp_path / "app" / "config.py").write_text("TIMEOUT = 30\n", encoding="utf-8")
    (tmp_path / "app" / "main.py").write_text(
        "from . import config\nfrom app import broken\nimport httpx\n", encoding="utf-8"
    )

    analysis = AnalysisService().analyze_repository(tmp_path)
    classified = {
        file.path: file for file in classify_imports(to_analyzed_files(analysis))
    }

    assert classified["app/__init__.py"].parsed is False
    assert _imports(classified["app/main.py"]) == [
        (".", "internal", "app/config.py"),
        ("app", "internal", "app/__init__.py"),
        ("httpx", "external", "httpx"),
    ]

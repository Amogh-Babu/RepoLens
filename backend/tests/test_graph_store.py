"""Unit tests for the SQLite graph schema and SqliteGraphStore (#23, #35)."""

import time
import pytest

from repolens.graph import (
    AnalysisCounts,
    AnalysisErrorRecord,
    AnalysisExpiredError,
    AnalysisNotFoundError,
    AnalysisNotReadyError,
    AnalysisRecord,
    AnalyzedFile,
    CommentRecord,
    FileNotFoundInAnalysisError,
    ImportRecord,
    SqliteGraphStore,
    SymbolRecord,
    build_github_source_url,
    infer_module_display_name,
    infer_module_id,
)


def _sample_analysis(
    analysis_id: str = "analysis-1",
    *,
    status: str = "completed",
    created_at: float = 0.0,
    expires_at: float = 0.0,
) -> AnalysisRecord:
    return AnalysisRecord(
        analysis_id=analysis_id,
        repo="https://github.com/octocat/hello-world.git",
        ref="main",
        sha="0123456789abcdef0123456789abcdef01234567",
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        expires_at=expires_at,
        counts=AnalysisCounts(analyzed=3, excluded=2, unparsed=1),
        files=(
            AnalyzedFile(
                path="manage.py",
                parsed=True,
                line_count=20,
                symbols=(SymbolRecord(name="main", kind="function", line=5),),
                imports=(
                    ImportRecord(
                        raw_name="app.service",
                        kind="internal",
                        target_path="app/service.py",
                    ),
                    ImportRecord(
                        raw_name="click",
                        kind="external",
                        target_package="click",
                    ),
                ),
                comments=(CommentRecord(line=1, text="CLI entrypoint"),),
            ),
            AnalyzedFile(
                path="app/service.py",
                parsed=True,
                line_count=45,
                symbols=(
                    SymbolRecord(name="AuthService", kind="class", line=10),
                    SymbolRecord(name="DEFAULT_TIMEOUT", kind="variable", line=3),
                ),
                imports=(
                    ImportRecord(
                        raw_name="dynamic.plugin",
                        kind="unresolved",
                    ),
                ),
                comments=(CommentRecord(line=9, text="Handles authentication"),),
            ),
            AnalyzedFile(
                path="app/broken.py",
                parsed=False,
                line_count=12,
                symbols=(),
                imports=(
                    ImportRecord(
                        raw_name="app.service",
                        kind="internal",
                        target_path="app/service.py",
                    ),
                ),
            ),
        ),
    )


def test_save_and_load_graph_round_trip() -> None:
    store = SqliteGraphStore()
    store.save(_sample_analysis())

    graph = store.get_graph("analysis-1")
    assert graph.analysis_id == "analysis-1"
    assert graph.repo == "https://github.com/octocat/hello-world"
    assert graph.sha == "0123456789abcdef0123456789abcdef01234567"

    assert len(graph.files) == 3
    assert [(m.id, m.name, m.file_paths) for m in graph.modules] == [
        (".", "(root)", ("manage.py",)),
        ("app", "app", ("app/service.py", "app/broken.py")),
    ]

    # Only parsed internal imports become edges
    assert len(graph.edges) == 1
    assert graph.edges[0].source == "manage.py"
    assert graph.edges[0].target == "app/service.py"


def test_save_and_load_file_detail_and_reverse_importers() -> None:
    store = SqliteGraphStore()
    store.save(_sample_analysis())

    manage = store.get_file("analysis-1", "manage.py")
    assert manage.path == "manage.py"
    assert manage.module == "."
    assert manage.parsed is True
    assert manage.line_count == 20
    assert (
        manage.source_url
        == "https://github.com/octocat/hello-world/blob/0123456789abcdef0123456789abcdef01234567/manage.py"
    )
    assert len(manage.symbols) == 1
    assert manage.symbols[0].name == "main"
    assert manage.symbols[0].source_url.endswith("/manage.py#L5")
    assert len(manage.internal_imports) == 1
    assert manage.internal_imports[0].target_path == "app/service.py"
    assert len(manage.external_imports) == 1
    assert manage.external_imports[0].package == "click"

    service = store.get_file("analysis-1", "app/service.py")
    assert service.imported_by == ("manage.py",)
    assert service.unresolved_imports == ("dynamic.plugin",)
    # Symbols ordered by line ASC
    assert [s.name for s in service.symbols] == ["DEFAULT_TIMEOUT", "AuthService"]


def test_save_overwrites_existing_analysis_atomically() -> None:
    store = SqliteGraphStore()
    store.save(_sample_analysis("analysis-dup"))

    replacement = AnalysisRecord(
        analysis_id="analysis-dup",
        repo="https://github.com/octocat/hello-world",
        sha="fedcba9876543210fedcba9876543210fedcba98",
        files=(AnalyzedFile(path="only_file.py", line_count=5),),
    )
    store.save(replacement)

    graph = store.get_graph("analysis-dup")
    assert [f.path for f in graph.files] == ["only_file.py"]
    with pytest.raises(FileNotFoundInAnalysisError):
        store.get_file("analysis-dup", "manage.py")


def test_expiry_and_eviction() -> None:
    now = time.time()
    store = SqliteGraphStore()
    store.save(
        _sample_analysis(
            "expired-1",
            created_at=now - 90_000,
            expires_at=now - 10,
        )
    )
    store.save(
        _sample_analysis(
            "active-1",
            created_at=now,
            expires_at=now + 3600,
        )
    )

    with pytest.raises(AnalysisExpiredError) as exc_info:
        store.get_graph("expired-1")
    assert exc_info.value.code == "ANALYSIS_EXPIRED"
    assert exc_info.value.status_code == 410

    evicted = store.evict_expired(now=now)
    assert evicted == 1

    with pytest.raises(AnalysisNotFoundError):
        store.get_graph("expired-1")

    assert store.get_graph("active-1").analysis_id == "active-1"


def test_not_ready_and_failed_analysis_lifecycle() -> None:
    store = SqliteGraphStore()
    store.save(_sample_analysis("queued-1", status="queued"))

    with pytest.raises(AnalysisNotReadyError) as exc_info:
        store.get_graph("queued-1")
    assert exc_info.value.code == "ANALYSIS_NOT_READY"
    assert exc_info.value.status_code == 409

    store.cancel_analysis("queued-1")
    assert store.get_analysis("queued-1")["status"] == "cancelled"

    failed = AnalysisRecord(
        analysis_id="failed-1",
        repo="https://github.com/octocat/empty",
        sha="0" * 40,
        status="failed",
        error=AnalysisErrorRecord(
            code="REPO_EMPTY",
            message="Repository is empty.",
            hint=None,
        ),
    )
    store.save(failed)
    info = store.get_analysis("failed-1")
    assert info["status"] == "failed"
    assert info["summary"] is None
    assert info["error"] == {
        "code": "REPO_EMPTY",
        "message": "Repository is empty.",
        "hint": None,
    }


def test_module_and_github_url_helpers() -> None:
    assert infer_module_id("manage.py") == "."
    assert infer_module_display_name(".") == "(root)"
    assert infer_module_id("app/auth/views.py") == "app/auth"
    assert infer_module_display_name("app/auth") == "auth"
    assert (
        build_github_source_url("octocat/hello-world", "abc1234", "/app/main.py", 42)
        == "https://github.com/octocat/hello-world/blob/abc1234/app/main.py#L42"
    )

"""Integration tests connecting SqliteGraphStore to SearchService and the HTTP search API (#29)."""

import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from repolens.api.search import install_search_api
from repolens.graph import (
    AnalysisRecord,
    AnalyzedFile,
    CommentRecord,
    ImportRecord,
    SqliteGraphStore,
    SymbolRecord,
)
from repolens.search import AnalysisUnavailableError, SearchService


_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "search_mini_repo"


def _seed_mini_repo_in_graph_store(store: SqliteGraphStore) -> str:
    data = json.loads(
        (_FIXTURE_ROOT / "search_index.json").read_text(encoding="utf-8")
    )
    analysis_id: str = data["analysis_id"]

    ref_to_target = {
        "app.authentication.service.login_user": "app/authentication/service.py",
        "app.users.repository.find_account": "app/users/repository.py",
    }

    files: list[AnalyzedFile] = []
    for doc in data["documents"]:
        symbols = tuple(
            SymbolRecord(name=sym, kind="function", line=idx * 5 + 1)
            for idx, sym in enumerate(doc["symbols"])
        )
        imports = tuple(
            ImportRecord(
                raw_name=ref,
                kind="internal",
                target_path=ref_to_target[ref],
            )
            for ref in doc["references"]
        )
        comments = tuple(
            CommentRecord(line=idx + 1, text=text)
            for idx, text in enumerate(doc["comments"])
        )
        files.append(
            AnalyzedFile(
                path=doc["path"],
                parsed=True,
                line_count=20,
                symbols=symbols,
                imports=imports,
                comments=comments,
            )
        )

    store.save(
        AnalysisRecord(
            analysis_id=analysis_id,
            repo="https://github.com/repolens-demo/search-mini-repo",
            sha="a" * 40,
            files=tuple(files),
        )
    )
    return analysis_id


def test_graph_store_satisfies_search_index_and_matches_reference_cases() -> None:
    store = SqliteGraphStore()
    analysis_id = _seed_mini_repo_in_graph_store(store)
    service = SearchService(store)

    cases = json.loads(
        (_FIXTURE_ROOT / "search_cases.json").read_text(encoding="utf-8")
    )
    for case in cases:
        page = service.search(analysis_id, case["query"])
        assert [item.path for item in page.results] == case["expected_paths"]


def test_graph_store_raises_analysis_unavailable_for_missing_or_expired() -> None:
    store = SqliteGraphStore()
    service = SearchService(store)

    with pytest.raises(AnalysisUnavailableError):
        service.search("missing-analysis", "login")


def test_search_endpoint_backed_by_sqlite_graph_store() -> None:
    store = SqliteGraphStore()
    analysis_id = _seed_mini_repo_in_graph_store(store)

    # 1. Standalone search router via install_search_api
    standalone_app = FastAPI()
    install_search_api(standalone_app, SearchService(store))
    standalone_client = TestClient(standalone_app)

    res = standalone_client.get(
        f"/analyses/{analysis_id}/search",
        params={"q": "authentication"},
    )
    assert res.status_code == 200
    assert [r["path"] for r in res.json()["results"]] == [
        "app/authentication/__init__.py",
        "app/users/repository.py",
        "app/authentication/service.py",
        "app/authentication/routes.py",
    ]


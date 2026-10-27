"""Demo FastAPI server backed by SqliteGraphStore with pre-seeded reference repos.

Run from the repository root:
    .venv/bin/uvicorn examples.full_api_demo:app --app-dir backend --reload
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from repolens.api.app import create_app
from repolens.graph import (
    AnalysisCounts,
    AnalysisRecord,
    AnalyzedFile,
    CommentRecord,
    ImportRecord,
    SqliteGraphStore,
    SymbolRecord,
)


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_mini_repo"
)


def _build_flask_files() -> tuple[AnalyzedFile, ...]:
    return (
        AnalyzedFile(
            path="manage.py",
            parsed=True,
            line_count=24,
            symbols=(SymbolRecord(name="main", kind="function", line=9),),
            imports=(
                ImportRecord(
                    raw_name="click", kind="external", target_package="click"
                ),
                ImportRecord(
                    raw_name="app",
                    kind="internal",
                    target_path="app/__init__.py",
                ),
            ),
            comments=(
                CommentRecord(
                    line=1, text="Command-line entry point for the app."
                ),
            ),
        ),
        AnalyzedFile(
            path="app/__init__.py",
            parsed=True,
            line_count=31,
            symbols=(SymbolRecord(name="create_app", kind="function", line=8),),
            imports=(
                ImportRecord(
                    raw_name="flask", kind="external", target_package="flask"
                ),
                ImportRecord(
                    raw_name="app.config",
                    kind="internal",
                    target_path="app/config.py",
                ),
                ImportRecord(
                    raw_name="app.auth.views",
                    kind="internal",
                    target_path="app/auth/views.py",
                ),
            ),
            comments=(
                CommentRecord(
                    line=7,
                    text="Application factory: registers the auth blueprint.",
                ),
            ),
        ),
        AnalyzedFile(
            path="app/config.py",
            parsed=True,
            line_count=18,
            symbols=(
                SymbolRecord(name="Config", kind="class", line=4),
                SymbolRecord(name="SECRET_KEY", kind="variable", line=5),
            ),
            imports=(
                ImportRecord(raw_name="os", kind="external", target_package="os"),
            ),
            comments=(
                CommentRecord(
                    line=3, text="Settings read from environment variables."
                ),
            ),
        ),
        AnalyzedFile(
            path="app/auth/views.py",
            parsed=True,
            line_count=68,
            symbols=(
                SymbolRecord(name="auth_bp", kind="variable", line=7),
                SymbolRecord(name="login", kind="function", line=11),
                SymbolRecord(name="logout", kind="function", line=34),
            ),
            imports=(
                ImportRecord(
                    raw_name="flask", kind="external", target_package="flask"
                ),
                ImportRecord(
                    raw_name="app.auth.service",
                    kind="internal",
                    target_path="app/auth/service.py",
                ),
            ),
            comments=(
                CommentRecord(
                    line=10,
                    text="Login form: checks credentials, then sets a token.",
                ),
            ),
        ),
        AnalyzedFile(
            path="app/auth/service.py",
            parsed=True,
            line_count=54,
            symbols=(
                SymbolRecord(name="authenticate", kind="function", line=9),
                SymbolRecord(name="login_user", kind="function", line=22),
            ),
            imports=(
                ImportRecord(
                    raw_name="app.config",
                    kind="internal",
                    target_path="app/config.py",
                ),
            ),
            comments=(
                CommentRecord(
                    line=8,
                    text="Authentication logic shared by views and routes.",
                ),
            ),
        ),
        AnalyzedFile(
            path="app/utils/broken.py",
            parsed=False,
            line_count=9,
        ),
    )


def _seed_store(store: SqliteGraphStore) -> None:
    # 1. Seed flask-auth-demo
    store.save(
        AnalysisRecord(
            analysis_id="flask-auth-demo",
            repo="https://github.com/repolens-demo/flask-auth",
            sha="3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f",
            status="completed",
            counts=AnalysisCounts(analyzed=5, excluded=2, unparsed=1),
            files=_build_flask_files(),
        )
    )

    # 2. Seed mini-repo-fixture
    data = json.loads(
        (_FIXTURE_ROOT / "search_index.json").read_text(encoding="utf-8")
    )
    ref_to_target = {
        "app.authentication.service.login_user": "app/authentication/service.py",
        "app.users.repository.find_account": "app/users/repository.py",
    }
    mini_files = tuple(
        AnalyzedFile(
            path=doc["path"],
            parsed=True,
            line_count=20,
            symbols=tuple(
                SymbolRecord(name=sym, kind="function", line=idx * 5 + 1)
                for idx, sym in enumerate(doc["symbols"])
            ),
            imports=tuple(
                ImportRecord(
                    raw_name=ref,
                    kind="internal",
                    target_path=ref_to_target[ref],
                )
                for ref in doc["references"]
            ),
            comments=tuple(
                CommentRecord(line=idx + 1, text=text)
                for idx, text in enumerate(doc["comments"])
            ),
        )
        for doc in data["documents"]
    )
    store.save(
        AnalysisRecord(
            analysis_id=data["analysis_id"],
            repo="https://github.com/repolens-demo/search-mini-repo",
            sha="0123456789abcdef0123456789abcdef01234567",
            status="completed",
            counts=AnalysisCounts(analyzed=len(mini_files), excluded=0, unparsed=0),
            files=mini_files,
        )
    )


class DemoAnalysisRunner:
    """Runner for local manual testing that immediately populates a completed graph."""

    def start(
        self,
        store: SqliteGraphStore,
        repo_url: str,
        ref: str | None,
    ) -> dict[str, Any]:
        clean_ref = ref.strip() if ref and ref.strip() else None
        sha = (
            clean_ref.lower()
            if clean_ref and len(clean_ref) == 40
            else hashlib.sha1(
                f"{repo_url}@{clean_ref or 'HEAD'}".encode("utf-8")
            ).hexdigest()
        )
        cached = store.find_cached_analysis(repo_url, sha)
        if cached is not None:
            return {
                "analysisId": str(cached["id"]),
                "sha": str(cached["sha"]),
                "status": "completed",
            }

        analysis_id = f"demo-{sha[:8]}"
        store.save(
            AnalysisRecord(
                analysis_id=analysis_id,
                repo=repo_url,
                ref=clean_ref,
                sha=sha,
                status="completed",
                counts=AnalysisCounts(analyzed=5, excluded=2, unparsed=1),
                files=_build_flask_files(),
            )
        )
        return {
            "analysisId": analysis_id,
            "sha": sha,
            "status": "completed",
        }


store = SqliteGraphStore()
_seed_store(store)
app = create_app(store, runner=DemoAnalysisRunner())

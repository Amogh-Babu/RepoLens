"""Validation tests for graph edges, module groups, and GitHub source links (#43, #35)."""

from repolens.graph import (
    AnalysisCounts,
    AnalysisRecord,
    AnalyzedFile,
    CommentRecord,
    ImportRecord,
    SqliteGraphStore,
    SymbolRecord,
)


FLASK_AUTH_SHA = "3f9c2a1e7b4d8c6f0a5e2b9d1c4f7a8e6b3d0c2f"
FLASK_AUTH_REPO_URL = "https://github.com/repolens-demo/flask-auth"


def build_flask_auth_record(analysis_id: str = "flask-auth-ref") -> AnalysisRecord:
    """Build the reference Flask auth repository matching frontend/src/api/mock/fixtureRepo.ts."""
    return AnalysisRecord(
        analysis_id=analysis_id,
        repo=FLASK_AUTH_REPO_URL,
        sha=FLASK_AUTH_SHA,
        counts=AnalysisCounts(analyzed=14, excluded=7, unparsed=1),
        files=(
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
                symbols=(
                    SymbolRecord(name="create_app", kind="function", line=8),
                ),
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
                        raw_name="app.db",
                        kind="internal",
                        target_path="app/db.py",
                    ),
                    ImportRecord(
                        raw_name="app.routes",
                        kind="internal",
                        target_path="app/routes.py",
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
                    SymbolRecord(
                        name="TOKEN_TTL_SECONDS", kind="variable", line=6
                    ),
                ),
                imports=(
                    ImportRecord(
                        raw_name="os", kind="external", target_package="os"
                    ),
                ),
                comments=(
                    CommentRecord(
                        line=3, text="Settings read from environment variables."
                    ),
                ),
            ),
            AnalyzedFile(
                path="app/db.py",
                parsed=True,
                line_count=42,
                symbols=(
                    SymbolRecord(name="get_db", kind="function", line=10),
                    SymbolRecord(name="init_db", kind="function", line=24),
                ),
                imports=(
                    ImportRecord(
                        raw_name="sqlite3",
                        kind="external",
                        target_package="sqlite3",
                    ),
                ),
                comments=(
                    CommentRecord(
                        line=9, text="One SQLite connection per request."
                    ),
                ),
            ),
            AnalyzedFile(
                path="app/routes.py",
                parsed=True,
                line_count=37,
                symbols=(
                    SymbolRecord(name="index", kind="function", line=8),
                    SymbolRecord(name="dashboard", kind="function", line=15),
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
                        line=14, text="Dashboard requires a logged-in user."
                    ),
                ),
            ),
            AnalyzedFile(
                path="app/auth/__init__.py",
                parsed=True,
                line_count=1,
            ),
            AnalyzedFile(
                path="app/auth/views.py",
                parsed=True,
                line_count=68,
                symbols=(
                    SymbolRecord(name="auth_bp", kind="variable", line=7),
                    SymbolRecord(name="login", kind="function", line=11),
                    SymbolRecord(name="logout", kind="function", line=34),
                    SymbolRecord(name="register", kind="function", line=42),
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
                    ImportRecord(
                        raw_name="app.models.user",
                        kind="internal",
                        target_path="app/models/user.py",
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
                    SymbolRecord(name="logout_user", kind="function", line=36),
                    SymbolRecord(name="current_user", kind="function", line=44),
                ),
                imports=(
                    ImportRecord(
                        raw_name="app.models.user",
                        kind="internal",
                        target_path="app/models/user.py",
                    ),
                    ImportRecord(
                        raw_name="app.auth.tokens",
                        kind="internal",
                        target_path="app/auth/tokens.py",
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
                path="app/auth/tokens.py",
                parsed=True,
                line_count=33,
                symbols=(
                    SymbolRecord(name="create_token", kind="function", line=8),
                    SymbolRecord(name="verify_token", kind="function", line=19),
                ),
                imports=(
                    ImportRecord(
                        raw_name="jwt", kind="external", target_package="jwt"
                    ),
                    ImportRecord(
                        raw_name="app.config",
                        kind="internal",
                        target_path="app/config.py",
                    ),
                ),
                comments=(
                    CommentRecord(line=7, text="Signed session tokens for login."),
                ),
            ),
            AnalyzedFile(
                path="app/models/__init__.py",
                parsed=True,
                line_count=1,
            ),
            AnalyzedFile(
                path="app/models/user.py",
                parsed=True,
                line_count=47,
                symbols=(
                    SymbolRecord(name="User", kind="class", line=9),
                    SymbolRecord(name="hash_password", kind="function", line=30),
                    SymbolRecord(name="check_password", kind="function", line=38),
                ),
                imports=(
                    ImportRecord(
                        raw_name="werkzeug.security",
                        kind="external",
                        target_package="werkzeug",
                    ),
                    ImportRecord(
                        raw_name="app.db",
                        kind="internal",
                        target_path="app/db.py",
                    ),
                ),
                comments=(
                    CommentRecord(
                        line=8, text="User model with password hashing."
                    ),
                ),
            ),
            AnalyzedFile(
                path="app/utils/strings.py",
                parsed=True,
                line_count=12,
                symbols=(SymbolRecord(name="slugify", kind="function", line=4),),
                imports=(
                    ImportRecord(
                        raw_name="re", kind="external", target_package="re"
                    ),
                ),
            ),
            AnalyzedFile(
                path="app/utils/broken.py",
                parsed=False,
                line_count=9,
            ),
            AnalyzedFile(
                path="app/legacy.py",
                parsed=True,
                line_count=15,
                symbols=(
                    SymbolRecord(name="load_plugins", kind="function", line=6),
                ),
                imports=(
                    ImportRecord(raw_name="plugins.loader", kind="unresolved"),
                ),
                comments=(
                    CommentRecord(
                        line=5, text="Old plugin system; not used by login."
                    ),
                ),
            ),
            AnalyzedFile(
                path="tests/test_auth.py",
                parsed=True,
                line_count=58,
                symbols=(
                    SymbolRecord(
                        name="test_login_success", kind="function", line=8
                    ),
                    SymbolRecord(
                        name="test_login_bad_password", kind="function", line=21
                    ),
                    SymbolRecord(name="test_logout", kind="function", line=35),
                ),
                imports=(
                    ImportRecord(
                        raw_name="pytest",
                        kind="external",
                        target_package="pytest",
                    ),
                    ImportRecord(
                        raw_name="app.auth.service",
                        kind="internal",
                        target_path="app/auth/service.py",
                    ),
                ),
                comments=(
                    CommentRecord(line=1, text="Tests for login and logout."),
                ),
            ),
        ),
    )


def test_validate_reference_repo_graph_edges_and_modules() -> None:
    store = SqliteGraphStore()
    store.save(build_flask_auth_record())

    graph = store.get_graph("flask-auth-ref")

    expected_modules = [
        (".", "(root)", ("manage.py",)),
        (
            "app",
            "app",
            (
                "app/__init__.py",
                "app/config.py",
                "app/db.py",
                "app/routes.py",
                "app/legacy.py",
            ),
        ),
        (
            "app/auth",
            "auth",
            (
                "app/auth/__init__.py",
                "app/auth/views.py",
                "app/auth/service.py",
                "app/auth/tokens.py",
            ),
        ),
        (
            "app/models",
            "models",
            ("app/models/__init__.py", "app/models/user.py"),
        ),
        (
            "app/utils",
            "utils",
            ("app/utils/strings.py", "app/utils/broken.py"),
        ),
        ("tests", "tests", ("tests/test_auth.py",)),
    ]
    assert [
        (m.id, m.name, m.file_paths) for m in graph.modules
    ] == expected_modules

    expected_edges = [
        ("manage.py", "app/__init__.py"),
        ("app/__init__.py", "app/config.py"),
        ("app/__init__.py", "app/db.py"),
        ("app/__init__.py", "app/routes.py"),
        ("app/__init__.py", "app/auth/views.py"),
        ("app/routes.py", "app/auth/service.py"),
        ("app/auth/views.py", "app/auth/service.py"),
        ("app/auth/views.py", "app/models/user.py"),
        ("app/auth/service.py", "app/models/user.py"),
        ("app/auth/service.py", "app/auth/tokens.py"),
        ("app/auth/tokens.py", "app/config.py"),
        ("app/models/user.py", "app/db.py"),
        ("tests/test_auth.py", "app/auth/service.py"),
    ]
    assert [(e.source, e.target) for e in graph.edges] == expected_edges


def test_validate_source_links_for_files_and_symbols() -> None:
    store = SqliteGraphStore()
    store.save(build_flask_auth_record())

    service_detail = store.get_file("flask-auth-ref", "app/auth/service.py")
    assert (
        service_detail.source_url
        == f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/auth/service.py"
    )
    assert service_detail.imported_by == (
        "app/routes.py",
        "app/auth/views.py",
        "tests/test_auth.py",
    )
    assert [
        (sym.name, sym.line, sym.source_url) for sym in service_detail.symbols
    ] == [
        (
            "authenticate",
            9,
            f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/auth/service.py#L9",
        ),
        (
            "login_user",
            22,
            f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/auth/service.py#L22",
        ),
        (
            "logout_user",
            36,
            f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/auth/service.py#L36",
        ),
        (
            "current_user",
            44,
            f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/auth/service.py#L44",
        ),
    ]

    broken_detail = store.get_file("flask-auth-ref", "app/utils/broken.py")
    assert broken_detail.parsed is False
    assert (
        broken_detail.source_url
        == f"{FLASK_AUTH_REPO_URL}/blob/{FLASK_AUTH_SHA}/app/utils/broken.py"
    )
    assert broken_detail.symbols == ()
    assert broken_detail.imports == ()

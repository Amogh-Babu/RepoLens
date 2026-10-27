"""SQLite implementation of the RepoLens graph store."""

from collections import defaultdict
from datetime import datetime, timezone
import sqlite3
import time

from repolens.graph.models import (
    AnalysisRecord,
    DependencyGraph,
    ExternalImportDetail,
    FileDetail,
    GraphEdge,
    GraphNode,
    ImportKind,
    ImportRecord,
    InternalImportDetail,
    ModuleGroup,
    SymbolDetail,
)
from repolens.graph.schema import init_schema
from repolens.search.models import SearchDocument
from repolens.search.ports import AnalysisUnavailableError


DEFAULT_TTL_SECONDS = 24 * 60 * 60


class GraphStoreError(LookupError):
    """Base error raised by the graph store with structured API fields."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code

    def to_dict(self) -> dict[str, str | None]:
        """Serialize error into the standard {code, message, hint} shape."""
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


class AnalysisNotFoundError(GraphStoreError, AnalysisUnavailableError):
    """Raised when an analysis ID does not exist in the store."""

    def __init__(self, analysis_id: str) -> None:
        super().__init__(
            code="ANALYSIS_NOT_FOUND",
            message=f"Analysis '{analysis_id}' was not found.",
            hint="Start a new analysis from the home page.",
            status_code=404,
        )


class AnalysisExpiredError(GraphStoreError, AnalysisUnavailableError):
    """Raised when a cached analysis has passed its 24-hour TTL."""

    def __init__(self, analysis_id: str) -> None:
        super().__init__(
            code="ANALYSIS_EXPIRED",
            message=f"Analysis '{analysis_id}' has expired.",
            hint="Re-analyze the repository URL and commit.",
            status_code=410,
        )


class AnalysisNotReadyError(GraphStoreError, AnalysisUnavailableError):
    """Raised when graph, file, or search queries run before analysis completes."""

    def __init__(self, analysis_id: str) -> None:
        super().__init__(
            code="ANALYSIS_NOT_READY",
            message=f"Analysis '{analysis_id}' has not finished yet.",
            hint="Wait for the analysis to complete and try again.",
            status_code=409,
        )


class FileNotFoundInAnalysisError(GraphStoreError):
    """Raised when a requested file path is not part of an analysis."""

    def __init__(self, analysis_id: str, path: str) -> None:
        super().__init__(
            code="FILE_NOT_FOUND",
            message=f"File '{path}' was not found in analysis '{analysis_id}'.",
            hint="Select a file from the explorer or dependency map.",
            status_code=404,
        )


def normalize_repo_url(repo: str) -> str:
    """Normalize a GitHub repository reference to https://github.com/<owner>/<repo>."""
    normalized_repo = repo.strip().rstrip("/")
    if normalized_repo.endswith(".git"):
        normalized_repo = normalized_repo[:-4]
    if not normalized_repo.startswith(("http://", "https://")):
        normalized_repo = f"https://github.com/{normalized_repo.lstrip('/')}"
    return normalized_repo


def _default_module(path: str, explicit_module: str = "") -> str:
    return explicit_module.strip() or "."



def _to_iso8601(timestamp: float) -> str:
    """Format a POSIX timestamp in seconds as an ISO-8601 UTC string."""
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class SqliteGraphStore:
    """SQLite-backed store for repository dependency graphs."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        init_schema(self._conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def save(self, analysis: AnalysisRecord) -> None:
        """Save an entire repository analysis in one atomic transaction."""
        now = time.time()
        created_at = analysis.created_at if analysis.created_at > 0 else now
        expires_at = (
            analysis.expires_at
            if analysis.expires_at > 0
            else created_at + DEFAULT_TTL_SECONDS
        )

        analyzed_count = analysis.counts.analyzed or len(analysis.files)
        unparsed_count = analysis.counts.unparsed or sum(
            1 for f in analysis.files if not f.parsed
        )
        excluded_count = analysis.counts.excluded
        repo_url = normalize_repo_url(analysis.repo)

        error_code = analysis.error.code if analysis.error else None
        error_message = analysis.error.message if analysis.error else None
        error_hint = analysis.error.hint if analysis.error else None

        with self._conn:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute(
                "DELETE FROM analyses WHERE id = ?;",
                (analysis.analysis_id,),
            )
            self._conn.execute(
                """
                INSERT INTO analyses (
                    id, repo, ref, sha, status, stage, from_cache,
                    created_at, expires_at,
                    analyzed_count, excluded_count, unparsed_count,
                    error_code, error_message, error_hint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    analysis.analysis_id,
                    repo_url,
                    analysis.ref,
                    analysis.sha,
                    analysis.status,
                    analysis.stage,
                    1 if analysis.from_cache else 0,
                    created_at,
                    expires_at,
                    analyzed_count,
                    excluded_count,
                    unparsed_count,
                    error_code,
                    error_message,
                    error_hint,
                ),
            )

            path_to_file_id: dict[str, int] = {}
            for file_rec in analysis.files:
                module_id = _default_module(file_rec.path, file_rec.module)
                cursor = self._conn.execute(
                    """
                    INSERT INTO files (
                        analysis_id, path, module, parsed, line_count
                    ) VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        analysis.analysis_id,
                        file_rec.path,
                        module_id,
                        1 if file_rec.parsed else 0,
                        file_rec.line_count,
                    ),
                )
                file_id = int(cursor.lastrowid)
                path_to_file_id[file_rec.path] = file_id

            for file_rec in analysis.files:
                file_id = path_to_file_id[file_rec.path]

                if file_rec.symbols:
                    self._conn.executemany(
                        """
                        INSERT INTO symbols (file_id, name, kind, line)
                        VALUES (?, ?, ?, ?);
                        """,
                        [
                            (file_id, sym.name, sym.kind, sym.line)
                            for sym in file_rec.symbols
                        ],
                    )

                if file_rec.comments:
                    self._conn.executemany(
                        """
                        INSERT INTO comments (file_id, line, text)
                        VALUES (?, ?, ?);
                        """,
                        [
                            (file_id, com.line, com.text)
                            for com in file_rec.comments
                        ],
                    )

                if file_rec.parsed and file_rec.imports:
                    import_rows = []
                    for imp in file_rec.imports:
                        target_file_id = (
                            path_to_file_id.get(imp.target_path)
                            if imp.kind == "internal" and imp.target_path
                            else None
                        )
                        import_rows.append(
                            (
                                file_id,
                                imp.raw_name,
                                imp.kind,
                                target_file_id,
                                imp.target_package,
                            )
                        )
                    self._conn.executemany(
                        """
                        INSERT INTO imports (
                            file_id, raw_name, kind, target_file_id, target_package
                        ) VALUES (?, ?, ?, ?, ?);
                        """,
                        import_rows,
                    )

    def find_cached_analysis(
        self,
        repo: str,
        sha: str,
        now: float | None = None,
    ) -> sqlite3.Row | None:
        """Find a completed, non-expired analysis row for (repo, sha)."""
        cutoff = now if now is not None else time.time()
        repo_url = normalize_repo_url(repo)
        return self._conn.execute(
            """
            SELECT * FROM analyses
            WHERE repo = ? AND sha = ? AND status = 'completed' AND expires_at > ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (repo_url, sha, cutoff),
        ).fetchone()

    def cancel_analysis(self, analysis_id: str) -> None:
        """Cancel a queued or running analysis."""
        row = self._get_valid_analysis_row(analysis_id, require_completed=False)
        if row["status"] in ("queued", "running"):
            with self._conn:
                self._conn.execute(
                    "UPDATE analyses SET status = 'cancelled', stage = NULL WHERE id = ?;",
                    (analysis_id,),
                )

    def get_analysis(self, analysis_id: str) -> dict[str, object]:
        """Return the Analysis response payload matching GET /analyses/{id}."""
        row = self._get_valid_analysis_row(analysis_id, require_completed=False)
        status = str(row["status"])
        summary = (
            {
                "filesAnalyzed": int(row["analyzed_count"]),
                "filesExcluded": int(row["excluded_count"]),
                "filesUnparsed": int(row["unparsed_count"]),
            }
            if status == "completed"
            else None
        )
        error = (
            {
                "code": str(row["error_code"]),
                "message": str(row["error_message"] or ""),
                "hint": str(row["error_hint"]) if row["error_hint"] is not None else None,
            }
            if status == "failed" and row["error_code"]
            else None
        )
        return {
            "analysisId": str(row["id"]),
            "repoUrl": str(row["repo"]),
            "ref": str(row["ref"]) if row["ref"] is not None else None,
            "sha": str(row["sha"]),
            "status": status,
            "stage": str(row["stage"]) if row["stage"] is not None else None,
            "summary": summary,
            "fromCache": bool(row["from_cache"]),
            "createdAt": _to_iso8601(float(row["created_at"])),
            "expiresAt": _to_iso8601(float(row["expires_at"])),
            "error": error,
        }

    def get_summary(self, analysis_id: str) -> dict[str, object]:
        """Return analysis status and summary counts for GET /analyses/{id}."""
        row = self._get_valid_analysis_row(analysis_id, require_completed=False)
        payload = self.get_analysis(analysis_id)
        payload["repo"] = str(row["repo"])
        payload["counts"] = {
            "analyzed": int(row["analyzed_count"]),
            "excluded": int(row["excluded_count"]),
            "unparsed": int(row["unparsed_count"]),
        }
        return payload

    def get_graph(self, analysis_id: str) -> DependencyGraph:
        """Return module groups, file nodes, and internal dependency edges."""
        analysis_row = self._get_valid_analysis_row(
            analysis_id, require_completed=True
        )

        file_rows = self._conn.execute(
            """
            SELECT id, path, module, parsed, line_count
            FROM files
            WHERE analysis_id = ?
            ORDER BY id ASC;
            """,
            (analysis_id,),
        ).fetchall()

        files: list[GraphNode] = []
        module_to_paths: dict[str, list[str]] = defaultdict(list)

        for row in file_rows:
            path = str(row["path"])
            module = str(row["module"])
            files.append(
                GraphNode(
                    path=path,
                    module=module,
                    parsed=bool(row["parsed"]),
                    line_count=int(row["line_count"]),
                )
            )
            module_to_paths[module].append(path)

        modules = tuple(
            ModuleGroup(
                id=mod,
                name=mod,
                file_paths=tuple(paths),
            )
            for mod, paths in module_to_paths.items()
        )

        edge_rows = self._conn.execute(
            """
            SELECT f.path AS source_path, tf.path AS target_path, i.raw_name
            FROM imports i
            JOIN files f ON i.file_id = f.id
            JOIN files tf ON i.target_file_id = tf.id
            WHERE f.analysis_id = ? AND i.kind = 'internal' AND f.parsed = 1
            ORDER BY f.id ASC, i.id ASC;
            """,
            (analysis_id,),
        ).fetchall()

        edges = tuple(
            GraphEdge(
                source=str(row["source_path"]),
                target=str(row["target_path"]),
                raw_name=str(row["raw_name"]),
            )
            for row in edge_rows
        )

        return DependencyGraph(
            analysis_id=analysis_id,
            repo=str(analysis_row["repo"]),
            sha=str(analysis_row["sha"]),
            modules=modules,
            files=tuple(files),
            edges=edges,
        )

    def get_file(self, analysis_id: str, path: str) -> FileDetail:
        """Return detailed metadata, symbols, imports, and importers for one file."""
        analysis_row = self._get_valid_analysis_row(
            analysis_id, require_completed=True
        )
        repo = str(analysis_row["repo"])
        sha = str(analysis_row["sha"])
        normalized_path = path.lstrip("/")

        file_row = self._conn.execute(
            """
            SELECT id, path, module, parsed, line_count
            FROM files
            WHERE analysis_id = ? AND path = ?;
            """,
            (analysis_id, normalized_path),
        ).fetchone()

        if file_row is None:
            raise FileNotFoundInAnalysisError(analysis_id, normalized_path)

        file_id = int(file_row["id"])
        file_path = str(file_row["path"])
        parsed = bool(file_row["parsed"])

        symbol_rows = self._conn.execute(
            """
            SELECT name, kind, line
            FROM symbols
            WHERE file_id = ?
            ORDER BY line ASC, name ASC;
            """,
            (file_id,),
        ).fetchall()

        symbols = tuple(
            SymbolDetail(
                name=str(row["name"]),
                kind=row["kind"],
                line=int(row["line"]),
                source_url="",
            )
            for row in symbol_rows
        )

        import_rows = self._conn.execute(
            """
            SELECT i.raw_name, i.kind, i.target_package, tf.path AS target_path
            FROM imports i
            LEFT JOIN files tf ON i.target_file_id = tf.id
            WHERE i.file_id = ?
            ORDER BY i.id ASC;
            """,
            (file_id,),
        ).fetchall()

        imports: list[ImportRecord] = []
        internal_imports: list[InternalImportDetail] = []
        external_imports: list[ExternalImportDetail] = []
        unresolved_imports: list[str] = []

        if parsed:
            for row in import_rows:
                kind_str = str(row["kind"])
                raw_name = str(row["raw_name"])
                if kind_str == "internal" and row["target_path"]:
                    target_path = str(row["target_path"])
                    imports.append(
                        ImportRecord(
                            raw_name=raw_name,
                            kind="internal",
                            target_path=target_path,
                            target_package=None,
                        )
                    )
                    internal_imports.append(
                        InternalImportDetail(
                            raw_name=raw_name,
                            target_path=target_path,
                        )
                    )
                elif kind_str == "external":
                    package = (
                        str(row["target_package"])
                        if row["target_package"]
                        else raw_name.split(".")[0]
                    )
                    imports.append(
                        ImportRecord(
                            raw_name=raw_name,
                            kind="external",
                            target_path=None,
                            target_package=package,
                        )
                    )
                    external_imports.append(
                        ExternalImportDetail(raw_name=raw_name, package=package)
                    )
                else:
                    imports.append(
                        ImportRecord(
                            raw_name=raw_name,
                            kind="unresolved",
                            target_path=None,
                            target_package=None,
                        )
                    )
                    unresolved_imports.append(raw_name)

        importer_rows = self._conn.execute(
            """
            SELECT DISTINCT f.path AS importer_path, f.id AS importer_id
            FROM imports i
            JOIN files f ON i.file_id = f.id
            WHERE i.target_file_id = ? AND i.kind = 'internal' AND f.parsed = 1
            ORDER BY f.id ASC;
            """,
            (file_id,),
        ).fetchall()

        imported_by = tuple(str(row["importer_path"]) for row in importer_rows)

        return FileDetail(
            analysis_id=analysis_id,
            repo=repo,
            sha=sha,
            path=file_path,
            module=str(file_row["module"]),
            parsed=parsed,
            line_count=int(file_row["line_count"]),
            source_url="",
            symbols=symbols,
            imports=tuple(imports),
            internal_imports=tuple(internal_imports),
            external_imports=tuple(external_imports),
            unresolved_imports=tuple(unresolved_imports),
            imported_by=imported_by,
        )

    def evict_expired(self, now: float | None = None) -> int:
        """Delete analyses whose expires_at timestamp has passed."""
        cutoff = now if now is not None else time.time()
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM analyses WHERE expires_at <= ?;",
                (cutoff,),
            )
            return int(cursor.rowcount)

    def _get_valid_analysis_row(
        self,
        analysis_id: str,
        *,
        require_completed: bool = False,
    ) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM analyses WHERE id = ?;",
            (analysis_id,),
        ).fetchone()
        if row is None:
            raise AnalysisNotFoundError(analysis_id)
        if float(row["expires_at"]) <= time.time():
            raise AnalysisExpiredError(analysis_id)
        if require_completed and str(row["status"]) != "completed":
            raise AnalysisNotReadyError(analysis_id)
        return row

# Backend

## Graph Schema and Storage (`repolens.graph`)

`repolens.graph` persists and queries repository dependency graphs in SQLite (`repolens.graph.schema` and `repolens.graph.store.SqliteGraphStore`), keyed by `analysis_id`.

### SQLite Tables
- **`analyses`**:
  - `id` (`TEXT PRIMARY KEY`): unique analysis identifier.
  - `repo` (`TEXT NOT NULL`), `ref` (`TEXT`), `sha` (`TEXT NOT NULL`): normalized GitHub repository URL, optional requested ref, and resolved commit SHA.
  - `status` (`TEXT NOT NULL`), `stage` (`TEXT`), `from_cache` (`INTEGER NOT NULL DEFAULT 0`): lifecycle state (`queued`, `running`, `completed`, `failed`, `cancelled`) and active pipeline stage.
  - `created_at` (`REAL NOT NULL`), `expires_at` (`REAL NOT NULL`): POSIX timestamps (24-hour TTL by default).
  - `analyzed_count`, `excluded_count`, `unparsed_count` (`INTEGER NOT NULL DEFAULT 0`): summary file counts.
  - `error_code`, `error_message`, `error_hint` (`TEXT`): structured failure metadata when `status = 'failed'`.
- **`files`**:
  - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`), `analysis_id` (`TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE`), `path` (`TEXT NOT NULL`), `module` (`TEXT NOT NULL`), `parsed` (`INTEGER NOT NULL DEFAULT 1`), `line_count` (`INTEGER NOT NULL DEFAULT 0`), `UNIQUE (analysis_id, path)`.
- **`symbols`**:
  - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`), `file_id` (`INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE`), `name` (`TEXT NOT NULL`), `kind` (`TEXT NOT NULL`: `function`, `class`, `variable`), `line` (`INTEGER NOT NULL`).
- **`imports`**:
  - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`), `file_id` (`INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE`), `raw_name` (`TEXT NOT NULL`), `kind` (`TEXT NOT NULL`: `internal`, `external`, `unresolved`), `target_file_id` (`INTEGER REFERENCES files(id) ON DELETE SET NULL`), `target_package` (`TEXT`).
- **`comments`**:
  - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`), `file_id` (`INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE`), `line` (`INTEGER NOT NULL`), `text` (`TEXT NOT NULL`).

All child tables cascade on `DELETE FROM analyses`, and indexes (`idx_analyses_repo_sha`, `idx_files_analysis_id`, `idx_symbols_file_id`, `idx_imports_file_id`, `idx_imports_target_file_id`, `idx_comments_file_id`) accelerate neighbor lookups and cache checks.

```python
from repolens.graph import AnalysisRecord, AnalyzedFile, SqliteGraphStore
from repolens.search import SearchService

store = SqliteGraphStore("repolens.db")
store.save(
    AnalysisRecord(
        analysis_id="analysis-1",
        repo="https://github.com/owner/repo",
        sha="0123456789abcdef0123456789abcdef01234567",
        files=(AnalyzedFile(path="app/main.py", line_count=20),),
    )
)
graph = store.get_graph("analysis-1")
detail = store.get_file("analysis-1", "app/main.py")
results = SearchService(store).search("analysis-1", "main")
```

## FastAPI Application and Endpoints (`repolens.api`)

`repolens.api.app.create_app(store, runner)` creates the unified FastAPI application whose OpenAPI schema matches `frontend/src/api/types.ts`:
- `POST /analyses` — Validates the GitHub URL, reuses a non-expired cached analysis for `(repo, sha)` or starts a new analysis, returning `{analysisId, sha, status}`.
- `GET /analyses/{analysis_id}` — Returns lifecycle status, active stage, summary counts, cache flag, ISO-8601 timestamps, and any structured error.
- `DELETE /analyses/{analysis_id}` — Cancels a queued or running analysis (`204 No Content`).
- `GET /analyses/{analysis_id}/graph` — Returns `{modules, files, edges}` for the interactive dependency map (`repolens.graph.endpoints`).
- `GET /analyses/{analysis_id}/files/{file_path:path}` — Returns `{path, module, parsed, lineCount, symbols, imports, importedBy, sourceUrl}` with pinned GitHub blob and `#L<line>` URLs.
- `GET /analyses/{analysis_id}/search` — Queries `SearchService(store)` and returns ranked files with 1-based reading-order `position` and match line numbers.

Run the main backend server locally from the repository root:

```bash
PYTHONPATH=backend python3 -m uvicorn repolens.api.app:app --app-dir backend --reload
```

## Search and Ranking

`repolens.search.SearchService` accepts the user's query and an `analysis_id`.
It asks an injected `SearchIndex` for normalized records, checks each path,
symbol, reference (such as an import), and comment for query terms, ranks the
matches using textual evidence and dependency relationships, and returns a
page of files with evidence and explanations. The query is not inferred by
the service; the API caller passes it from the search box.

The search records are language-neutral. An analyzer and graph adapter for
another language can map its paths, symbols, references, comments, and
dependency relationships to the same `SearchDocument` without changing
ranking. Search only reads the index; it does not download, parse, or execute
the source repository.

Reading order respects matched dependency edges: when one matched file
depends on another matched file, the dependency comes first. Among files whose
order is not constrained by dependencies, query relevance and then
case-insensitive path determine order. Cycles are handled deterministically.
The baseline field weights are 8 for paths, 6 for symbols, 4 for references,
and 2 for comments per matched term, plus 3 per distinct matched query term.
An additional 1.5 points per matching dependent breaks ties and informs the
reason; dependency order itself is enforced separately.

Queries are case-insensitive substring matches over distinct word terms and
are limited to 200 characters. Whitespace-only queries are rejected. The
default page size is 20 and the maximum is 100. Reasons are single-line and
cite up to two matching values; the full match list is returned separately.

## Search API

`repolens.api.search.install_search_api(app, search_service)` mounts
`GET /analyses/{analysis_id}/search?q=...&offset=0&limit=20`. A successful
response contains `results` (path, score, reason, and match evidence), `total`,
`offset`, `limit`, and `has_more`. Errors use the pitch's `{code, message,
hint}` shape. A missing or expired analysis returns `ANALYSIS_UNAVAILABLE`
with a re-analysis hint. Request validation is scoped to the search route and
does not override the host app's other API errors.

The production GraphStore adapter (`SqliteGraphStore`) implements the `SearchIndex`
protocol by returning `SearchDocument` records for the requested
analysis ID, and raising `AnalysisUnavailableError` when that analysis is
missing, expired, or not yet completed.

```python
from fastapi import FastAPI
from repolens.api.search import install_search_api
from repolens.graph import SqliteGraphStore
from repolens.search import SearchService

app = FastAPI()
store = SqliteGraphStore("repolens.db")
install_search_api(app, SearchService(store))
```

## Local Search Demo

The mini repository fixture contains authentication, user-account, and
billing files, a hand-annotated `search_index.json`, and expected reading
orders for representative queries. Its Python source is not executed. The
fixture index is a stand-in for the future analyzer/graph adapter, so this
demo exercises real HTTP/API/search behavior but does not ingest a Git repo.

Install backend and development dependencies from the repository root:

```bash
python3 -m pip install -r backend/requirements-dev.txt
```

Start the demo server:

```bash
PYTHONPATH=backend python3 -m uvicorn examples.search_demo:app --app-dir backend --reload
```

Search the mini repository in another terminal:

```bash
curl 'http://127.0.0.1:8000/analyses/mini-repo-fixture/search?q=authentication'
```

The fixture queries and expected orders are in
`backend/tests/fixtures/search_mini_repo/search_cases.json`.

## Tests

Backend tests use [pytest](https://docs.pytest.org/). From `backend/`:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

`pyproject.toml` puts `backend/` on the import path and points pytest at
`tests/`, so no `PYTHONPATH` is needed. Run one file with
`python -m pytest tests/test_search_scoring.py` or one test with `-k <name>`.

To add a test, create `tests/test_<feature>.py` and write functions named
`test_*` that use plain `assert`. Shared fixtures live in `tests/conftest.py`;
`test_search_scoring.py` is a short example. Existing `unittest.TestCase`
classes also run under pytest unchanged. The Backend GitHub Actions workflow
runs the whole suite on Python 3.11, 3.12, and 3.13 for every pull request that
touches `backend/`.

# Developers

This is a guide to the current implementation of RepoLens and the local workflow for contributing to it. The product overview and end-user walkthrough are in [‥/README.md](https://github.com/Amogh-Babu/RepoLens/blob/main/README.md).

## Architecture

RepoLens is a single-page React application backed by a FastAPI service. The browser communicates with the API over REST/JSON.

An analysis request resolves a GitHub reference to a commit SHA. It reuses a valid cached result when available. Otherwise, it starts the analysis pipeline, which fetches a repository snapshot, filters files, parses supported source files, resolves imports, adapts the results to graph records, and persists them in SQLite. Later graph, file-detail, and search requests read the stored analysis.

### Main request and analysis flow

1. `POST /analyses` validates a repository URL and resolves the requested branch, tag, or default branch to a full commit SHA.
2. The API looks for a completed, unexpired analysis keyed by `(repository, SHA)`. A cache hit is reused. Otherwise, the runner starts the work in a background thread.
3. `GitHubSource` downloads the archive for the resolved SHA. Archive extraction validates paths and refuses unsafe archive entries.
4. `SourceFileFilter` excludes vendored, generated, metadata, unsupported, and oversized files. The current repository limit is 5,000 analyzable files or 128 MiB of analyzable source. The default per-file limit is 2 MiB.
5. `AnalysisService` selects a registered `LanguageAnalyzer` by file extension. The current implementation registers `PythonAnalyzer` for `.py` and `.pyi` files.
6. The import classifier resolves against the repository file index. It labels imports `internal`, `external`, or `unresolved`.
7. The graph adapter converts the analysis to plain graph-store records. `SqliteGraphStore` writes the result to SQLite.
8. The frontend polls the analysis status endpoint. After completion, it requests graph, file-detail, and search data.

The analyzed repository's source is not retained as graph-store content. The temporary snapshot is cleaned up after processing. The UI links back to the original GitHub commit for source viewing.

## Repository layout

```text
.
├─ backend/
│  ├─ repolens/
│  │  ├─ api/          FastAPI application, routes, request validation
│  │  ├─ pipeline/     Analysis orchestration and runner
│  │  ├─ ingestion/    GitHub source, archive handling, filtering
│  │  ├─ analysis/     Language analyzers and import classification
│  │  ├─ graph/        SQLite schema, models, persistence, graph queries
│  │  ├─ search/       Search matching, ranking, and explanations
│  │  └─ common/       Shared records and error types
│  ├─ tests/           pytest tests and repository fixtures
│  └─ benchmarks/      Search and import-classification measurements
├─ frontend/
│  └─ src/
│     ├─ api/          Typed API clients and response models
│     ├─ state/        Client-side analysis, selection, and search state
│     ├─ components/   UI components
│     └─ pages/        Landing and analysis pages
├─ docs/
│  ├─ images/          Screenshots used by the user README
│  ├─ DEVELOPERS.md    This guide
│  └─ LivingDoc.md     Historical requirements/specification snapshot
├─ .github/workflows/  Backend, frontend, and release workflows
├─ Dockerfile
└─ compose.yaml
```

## Local development

### Prerequisites

* **Python 3.11 or newer.** The pinned version in [`.python-version`](.python-version) (3.12) is what the image and CI use; CI also runs the suite on 3.11 and the newest Python release.
* **[`uv`](https://docs.astral.sh/uv/getting-started/installation/)** to install the backend's locked dependencies. `uv` also downloads the pinned Python for you if it is missing, so you do not need `venv` or a system Python.
* **Node.js 22** and `npm` for the frontend (see [`.nvmrc`](.nvmrc)).

`make` is optional; every step below is a plain command.

### Install dependencies

Run from the repository root:

```bash
cd backend && uv sync --locked && cd ..
```

Then:

```bash
npm --prefix frontend ci
```

`uv sync --locked` creates the backend virtual environment `backend/.venv` with exactly the versions in
[`backend/uv.lock`](backend/uv.lock). Without `uv`,
`python -m pip install -r backend/requirements-dev.txt` installs the same pinned versions (the file is exported from the lockfile and checked in CI).

### Run the backend and frontend

Use two terminals to run the development servers.

In one terminal, to run the backend:

```bash
cd backend && uv run uvicorn repolens.api.app:app --reload --port 8000
```

The development API is available at http://127.0.0.1:8000; its interactive OpenAPI documentation is at http://127.0.0.1:8000/docs.

In the other terminal, from the repository root, to run the frontend:

```bash
npm --prefix frontend run dev
```

Open **http://localhost:5173**. The Vite dev server proxies API requests `/api/*` to the
backend on port 8000, and the API's interactive docs are at http://127.0.0.1:8000/docs. (On macOS/Linux, `make run` starts both.)

### Develop UI

To develop the UI without a running backend, create `frontend/.env.local` with:

```dotenv
VITE_API_MODE=mock
```

The mock API uses a small handwritten Flask authentication feature and synthetic repository names to exercise UI states. This is for frontend development, not for testing the real ingestion pipeline.

See
[`frontend/README.md`](frontend/README.md) and
[`backend/README.md`](backend/README.md) for component-specific options.

### Run with Docker

From the repository root, run:

```bash
docker compose up --build
```

The packaged app serves the frontend at http://localhost:8000 and mounts the API under `/api`. The database is stored in the `repolens-data` volume at `/data/repolens.db`. Optionally, use  the `GITHUB_TOKEN` environment variable to raise the GitHub API rate limit.

## Tests and quality checks

### Backend

From `backend/`, run:

```bash
uv run pytest
```

Run a focused test file or test name with, for example:

```bash
uv run pytest tests/test_search_scoring.py
uv run pytest -k ranking
```

The end-to-end reference-repository test can be selected with:

```bash
uv run pytest -m e2e
```

This exercises the pipeline through the API using a handwritten repository fixture and a fake GitHub transport. It checks the summary, graph, file-level symbols/imports, and expected reading orders.

### Frontend

From the repository root, run:

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Tests use Vitest and React Testing Library. Test files sit beside the module or component that they exercise, and use the mock API client.

### Docker image

From the repository root, run:

```bash
docker build --target test .
```

This builds the test stage and runs the backend suite in the container build environment.

### Update dependencies

Backend dependencies are locked. To upgrade them, move `exclude-newer` in
[`backend/pyproject.toml`](backend/pyproject.toml) to a recent date (keep it a
couple of weeks in the past), then run `uv lock` and re-export the
requirements files:

```bash
cd backend && uv lock && uv export --locked --no-dev --format requirements-txt --no-emit-project -o requirements.txt && uv export --locked --format requirements-txt --no-emit-project -o requirements-dev.txt
```

## Benchmarks

Benchmarks live in `backend/benchmarks/`. Run them from `backend/` after `uv sync --locked`:

```bash
uv run python -m benchmarks.search_precision
uv run python -m benchmarks.import_classification
```

To refresh a checked-in measurement record after intentionally changing search-indexing or import-resolution behavior, add `--write`, and include the before-and-after results and explanation in the pull request:

```bash
uv run python -m benchmarks.search_precision --write
uv run python -m benchmarks.import_classification --write
```

## SQLite schema

The schema is defined in `backend/repolens/graph/schema.py`. Graph-store records and allowed enum values are defined in `backend/repolens/graph/models.py`. Tables are created as SQLite `STRICT` tables when the linked SQLite library is version 3.37 or newer. On older SQLite versions, ordinary tables are used with the same explicit `CHECK` constraints.

| Table | Columns and declared SQLite types |
| --- | --- |
| `analyses` | `id TEXT PRIMARY KEY`; `repo TEXT NOT NULL`; `ref TEXT`; `sha TEXT NOT NULL`; `status TEXT NOT NULL`; `stage TEXT`; `from_cache INTEGER NOT NULL DEFAULT 0`; `created_at REAL NOT NULL`; `expires_at REAL NOT NULL`; `analyzed_count INTEGER NOT NULL DEFAULT 0`; `excluded_count INTEGER NOT NULL DEFAULT 0`; `unparsed_count INTEGER NOT NULL DEFAULT 0`; `error_code TEXT`; `error_message TEXT`; `error_hint TEXT`. |
| `files` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `analysis_id TEXT NOT NULL`; `path TEXT NOT NULL`; `module TEXT NOT NULL`; `parsed INTEGER NOT NULL DEFAULT 1`; `line_count INTEGER NOT NULL DEFAULT 0`. `(analysis_id, path)` is unique. |
| `symbols` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `file_id INTEGER NOT NULL`; `name TEXT NOT NULL`; `kind TEXT NOT NULL`; `line INTEGER NOT NULL`. |
| `imports` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `file_id INTEGER NOT NULL`; `raw_name TEXT NOT NULL`; `kind TEXT NOT NULL`; `target_file_id INTEGER`; `target_package TEXT`. |
| `comments` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `file_id INTEGER NOT NULL`; `line INTEGER NOT NULL`; `text TEXT NOT NULL`; `kind TEXT NOT NULL DEFAULT 'comment'`. |
| `members` | `id INTEGER PRIMARY KEY AUTOINCREMENT`; `file_id INTEGER NOT NULL`; `owner TEXT NOT NULL`; `name TEXT NOT NULL`; `kind TEXT NOT NULL`; `line INTEGER NOT NULL`. |

Important constraints and conventions:

- Booleans (`from_cache`, `parsed`) are stored as `INTEGER` values restricted to `0` or `1`.
- `created_at` and `expires_at` are `REAL` POSIX timestamps in seconds.
- Fixed-value fields use `CHECK` constraints: analysis status/stage, symbol kind (`function`, `class`, `variable`), import kind (`internal`, `external`, `unresolved`), comment kind (`comment`, `docstring`), and member kind (`method`, `attribute`).
- Child rows reference their parent rows with foreign keys. Deleting an analysis cascades to its files and related records; deleting a target file sets `imports.target_file_id` to `NULL`.
- Indexes support repository/SHA cache lookup and file-to-symbol/import/comment/member lookups.
- `SCHEMA_VERSION` is stored in `PRAGMA user_version`. The database is a disposable 24-hour cache, so a schema-version mismatch drops and rebuilds the cached tables rather than running migrations. Bump the schema version when changing the schema.

## Adding a language analyzer

The analyzer boundary is designed so that language-specific parser objects don't leak into the rest of the system. The current built-in analyzer is `PythonAnalyzer`, which uses Python's standard-library `ast` and `tokenize` modules and supports .py and .pyi files.

1. **Read the interface and neutral records.** Start with `backend/repolens/analysis/ports.py` and the analysis model/record definitions. A `LanguageAnalyzer` provides `language`, `file_extensions`, `supports(path)`, and `analyze(path, source) -> ParsedFile`.
2. **Implement the parser.** Add an analyzer class for the new language. Extract the information the shared model supports: imports/references, module-level symbols, class or type members where meaningful, comments/docstrings, parse status, and line numbers. Return plain RepoLens records. Do not return parser-library nodes or execute analyzed code.
3. **Register it with `AnalysisService`.** Pass the analyzer alongside `PythonAnalyzer` when constructing the service, following the existing registration pattern in the backend. Check how the pipeline constructs `AnalysisService` so the production runner uses the new analyzer.
4. **Handle import resolution deliberately.** The analyzer must emit enough structured information for the classifier to identify an import's form, module, imported names, and relative depth where relevant. If the new language has different module-resolution rules, add language-appropriate resolution behavior rather than applying Python import semantics blindly.
5. **Add focused fixtures and tests.** Cover valid files, malformed files, relative/module imports, standard-library or built-in references, third-party packages, and ambiguous/unresolved imports. Assert both the neutral parse records and the final classified graph records.
6. **Run the end-to-end and search checks.** Confirm the new file type flows into SQLite, graph/file-detail responses, and the search index. Update relevant benchmarks/fixtures and documentation. State clearly which file extensions and syntax features are supported.

An analyzer class alone does not make a language fully supported. Ingestion filters, import classification, graph mapping, and the frontend's displayed data all need to remain compatible with the shared records.

## Adding a repository host

The current `RepoSource` port is implemented by `GitHubSource`, so public GitHub is the only supported host. A new host would need its own source adapter that resolves refs, downloads a stable snapshot, and returns the common snapshot records. Keep URL validation, allowed download hosts, redirect checks, archive/path safety, limits, and source-link generation host-aware. Add tests for URL validation and safe extraction before advertising the host as supported.

## Continuous integration and delivery (CI/CD)

GitHub Actions workflows are in [`.github/workflows/`](.github/workflows/).

- **[`backend.yml`](.github/workflows/backend.yml)** checks that `backend/uv.lock` and the exported requirements files are current, runs `pytest` on the pinned Python from `.python-version` with the locked dependencies, runs a compatibility job on Python 3.11 (the minimum) and the newest Python release, and runs a dedicated end-to-end job that runs the full pipeline on a hand-written reference repository and compares the results against expected output.
- **[`frontend.yml`](.github/workflows/frontend.yml)** runs ESLint, Prettier format checks, TypeScript typechecking, Vitest, and the production build using the Node version in `.nvmrc`.
- **[`release.yml`](.github/workflows/release.yml)** builds and tests the Docker image, starts the container and smoke-tests the UI and API, and publishes `ghcr.io/amogh-babu/repolens:latest` plus a commit-SHA tag on pushes to `main`. It redeploys the hosted deployment only when the maintainer has configured the `DEPLOY_HOOK_URL` secret (for example, a Render deploy hook). Pull requests that touch the image will build and smoke-test it, but do not publish it.

The backend and frontend workflows run on pull requests and on pushes to `main` that modify their part of the repository; the release workflow runs on every push to `main` and on pull requests that change the image. All of them can also be started from the Actions tab (**Run workflow**).

A pull request should have passing checks applicable to its changed paths and a maintainer review before merge. Documentation-only changes may not trigger every component workflow because the workflows use path filters.

## Current implementation assumptions

- The current source adapter only supports public repositories on github.com.
- The current language analyzer supports Python `.py` and `.pyi` files; other languages are not yet advertised as supported.
- Repository analysis is static. Runtime imports, dynamic loading, and execution-dependent behavior cannot be reconstructed reliably.
- The default filter caps each file at 2 MiB, and the analyzable repository at 5,000 files and 128 MiB.
- Results are keyed by repository and resolved commit SHA and expire after 24 hours. Reusing a cache entry does not extend its expiry.
- The current graph store is SQLite and assumes a single application instance. It is not a distributed multi-writer database service.

## Operational use cases (first prototype status)

First-version implementations of all major system components (**React Frontend**, **FastAPI HTTP Layer**, **GitHub Ingestion & File Filtering**, **Python AST Analyzer & Import Classifier**, **SQLite Graph Store**, and **Search & Ranking Service**) are integrated and operational.

> **Prototype Note**: The use cases below represent our *first integrated prototype* and are still being refined, benchmarked, and evaluated. Some edge cases and interactions are not yet finalized and may be subject to bugs (see **§ Current Prototype Limitations & Ongoing Work** below).

### 1. Use Case 1: Analyze a Public Repository by URL and Commit *(Operational — Prototype)*
* **Components Touched**: React Landing Page (`RepoInputForm`) $\rightarrow$ FastAPI (`POST /analyses`, `GET /analyses/{id}`) $\rightarrow$ GitHub Ref Resolver & Archive Fetcher (`repolens.ingestion`) $\rightarrow$ Auto-generated/Vendored File Filter $\rightarrow$ Python AST Parser & Import Classifier (`repolens.analysis`) $\rightarrow$ SQLite Graph Store (`repolens.graph`) $\rightarrow$ Frontend Summary Bar, File Explorer, and Dependency Map.
* **How to Verify**:
  1. Run `docker compose up --build` and open **http://localhost:8000** (or start the development servers and open **http://localhost:5173**).
  2. Enter a public Python repository URL (e.g., `https://github.com/pallets/itsdangerous`) and click **Analyze**.
  3. Observe the pipeline stage indicator (`resolving` $\rightarrow$ `downloading` $\rightarrow$ `filtering` $\rightarrow$ `parsing` $\rightarrow$ `classifying` $\rightarrow$ `storing`) and the resulting summary bar (analyzed, excluded, and unparsed file counts), file explorer tree, and module dependency map.

### 2. Use Case 2: Search for a Feature and Get a Ranked Reading List *(Operational — Prototype)*
* **Components Touched**: React Search Bar & Reading List $\rightarrow$ FastAPI (`GET /analyses/{id}/search`) $\rightarrow$ `SearchService` (`repolens.search`) querying `SqliteGraphStore` (`SearchIndex`) $\rightarrow$ DependencyMap search highlighting.
* **How to Verify**:
  1. After Use Case 1 completes, type a feature keyword (e.g., `signer`, `serializer`, or `timed` for `pallets/itsdangerous`) into the search bar and submit.
  2. The backend matches filenames, symbols, class members, imports, docstrings, and comments (ignoring filler words such as "where" or "do" in a question), orders matched dependencies ahead of callers, and returns a ranked reading list with one-line explanations and expandable match evidence while highlighting matching files on the map.

### 3. Use Case 3: Explore the Dependency Map and Open a File's Source *(Operational — Prototype)*
* **Components Touched**: React Flow Dependency Map / File Explorer / Reading List $\rightarrow$ FastAPI (`GET /analyses/{id}/graph`, `GET /analyses/{id}/files/{path}`) $\rightarrow$ `SqliteGraphStore` $\rightarrow$ File Detail Panel & pinned GitHub source links.
* **How to Verify**:
  1. Click a collapsed module node on the dependency map to expand its files, or select a file from the file explorer or reading list.
  2. Inspect the **File Detail Panel** on the right (module name, extracted functions/classes/variables, internal imports, `imported by` dependents, and external libraries).
  3. Click **Open source on GitHub** (or click any symbol name) to open the exact file or `#L<line>` definition on GitHub pinned to the analyzed commit SHA.

### Current Prototype Limitations & Ongoing Work
Because this is an initial end-to-end prototype, several areas are still being hardened and may exhibit bugs:
* **Import Resolution Edge Cases**: Non-standard `sys.path` manipulations, dynamic imports, and complex multi-package/namespace repository layouts may classify some internal imports as `unresolved` or `external`.
* **Large Repository Performance & Layout**: Repositories approaching the 1,000-file cap or containing dense cross-module import graphs are still being benchmarked against the 3-minute ingestion target and 2-second map layout target.
* **Search Ranking Calibration**: Field weights and dependency tie-breaking heuristics are functional but still undergoing precision evaluation and tuning against hand-labeled queries.
* **Synchronous Pipeline Execution**: Analysis currently runs within the request lifecycle; concurrent request deduplication and background progress streaming are still being refined.

## Documentation and Links

* **Living document**: [RepoLens Requirements Specification (Google Docs)](https://docs.google.com/document/d/1ZTgu6tfoWwx9FWWS-5DqG5CtgXJ-zucDNXEEca_Qy4s/edit?tab=t.sql8ybk4ej5d#heading=h.18mw63g8e8ay) | [Snapshot in `docs/`](docs/LivingDoc.md)
* **Issue tracker**: [GitHub Issues](https://github.com/Amogh-Babu/RepoLens/issues)
* **Coding guidelines**: [`coding-guidelines.md`](coding-guidelines.md)
* **Component docs**: [`backend/README.md`](backend/README.md) | [`frontend/README.md`](frontend/README.md)

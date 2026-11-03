# Backend

## Repository Ingestion (`repolens.ingestion`)

`repolens.ingestion.GitHubSource` implements the `RepoSource` port: it
downloads one archive for a (repository URL, commit SHA) pair and extracts it
to a snapshot directory. Nothing from the repository is ever imported,
executed, or evaluated — archive members are written to disk as bytes.

```python
from pathlib import Path

from repolens.ingestion import GitHubSource

snapshot = GitHubSource().fetch_snapshot(
    "https://github.com/octocat/Hello-World",
    "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d",
    Path("/tmp/repolens/snapshot"),
)
# Snapshot(repo=..., sha=..., root='/tmp/repolens/snapshot', files=('README',))
```

### Validation and Safety Rules
- **URLs** (`repolens.ingestion.urls.parse_repo_url`) must be `https://github.com/<owner>/<repo>`
  (`www.github.com` and a trailing `.git` are accepted). Non-https schemes,
  other hosts, embedded credentials, ports, queries, fragments, and deep links
  such as `/tree/<ref>` are rejected before any network call.
- **Commit SHAs** (`normalize_commit_sha`) must be a full 40-character hex SHA,
  so a snapshot is always reproducible; branches and tags are resolved earlier
  in the pipeline.
- **Downloads** (`HttpsArchiveFetcher`) only open https URLs on the
  `codeload.github.com` allowlist, validate redirect targets against the same
  allowlist, apply a timeout, and abort once the body passes
  `ArchiveLimits.max_archive_bytes`.
- **Extraction** (`extract_zip_archive`) validates every member before writing
  one byte: absolute paths, Windows separators and drive letters, `..`
  traversal (zip slip), symlinks, device nodes, and encrypted entries are
  refused, and the resolved path is re-checked against the snapshot root. The
  shared `<repo>-<sha>/` wrapper directory GitHub adds is stripped.
- **Limits** (`ArchiveLimits`) cap the compressed download, the extracted byte
  total, the file count, and the request timeout, plus the reviewable source a
  snapshot may yield: `max_file_bytes` per file, and `max_analyzable_bytes` and
  `max_analyzable_file_count` for the repository.
- **Failures** leave nothing behind: the downloaded archive is always deleted,
  a partial snapshot is discarded, and extracting over a non-empty directory is
  refused.

Errors are `IngestionError` subclasses carrying the API's
`{code, message, hint}` shape via `to_dict()`: `INVALID_URL`,
`UNSUPPORTED_HOST`, `INVALID_SHA`, `DOWNLOAD_FAILED`, `ARCHIVE_TOO_LARGE`,
`INVALID_ARCHIVE`, `UNSAFE_ARCHIVE`, `DESTINATION_NOT_EMPTY`,
`FILE_TOO_LARGE`, and `REPOSITORY_TOO_LARGE`.

Injecting an `ArchiveFetcher` (`GitHubSource(fetcher=...)`) swaps the transport,
which is how the tests exercise downloads without touching the network.

### Vendored, Generated, and Oversized Files

`repolens.ingestion.SourceFileFilter` implements the `FileFilter` port and
decides which extracted files are the repository's own reviewable source.
Checked-in dependencies, build output, and generated bindings would otherwise
fill the dependency graph and the search index with results nobody is looking
for. Decisions are made from a repository-relative path and a file size only;
no file is opened, imported, executed, or evaluated.

- **Vendored** (`vendored`): `node_modules`, `vendor`, `vendored`,
  `third_party`, `site-packages`, `bower_components`, `.venv`, `Pods`, and the
  rest of `VENDORED_DIRECTORY_NAMES`, matched case-insensitively against every
  path component.
- **Generated** (`generated`): build and artifact directories
  (`build`, `dist`, `target`, `coverage`, `__generated__`, `*.egg-info`), lock
  files and manifests (`package-lock.json`, `yarn.lock`, `poetry.lock`,
  `Cargo.lock`, `go.sum`), and generated or minified file names
  (`*_pb2.py`, `*.pb.go`, `*.generated.ts`, `*_generated.py`, `*.min.js`,
  `*.js.map`, `*.pyc`).
- **Tool and version-control state** (`metadata`): `.git`, `.hg`, `.svn`,
  `__pycache__`, `.mypy_cache`, `.tox`, and similar.
- **Oversized** (`too_large`): a file past `ArchiveLimits.max_file_bytes`
  (2 MiB by default) is excluded. `require_file_within_limits` raises
  `FileTooLargeError` (`FILE_TOO_LARGE`) instead, for a caller that asked for
  one named file and needs to be told why it is not analyzed.
- **Oversized repositories**: `require_repository_within_limits(count, bytes)`
  raises `RepositoryTooLargeError` (`REPOSITORY_TOO_LARGE`) once the files
  being kept pass `max_analyzable_bytes` (128 MiB) or
  `max_analyzable_file_count` (20,000). It is the single enforcement point:
  `filter_files` and `filter_snapshot` call it while filtering a snapshot's
  file list, and `AnalysisService.analyze_repository` calls it with its running
  totals as it walks a checkout, so both paths reject an oversized repository
  rather than analyzing it. Filtered and unsupported files are not counted, so
  vendored code cannot push a small repository over the limit, and the check
  stops early instead of measuring the whole tree.

The `FileFilter` port is three methods: `exclusion_for(path, size_bytes)`
returns a `FileExclusion` (`path`, `reason`, `detail`) or `None`,
`directory_exclusion_for(path)` lets a tree walk prune a vendored directory
instead of visiting every file in it, and
`require_repository_within_limits(count, bytes)` applies the repository caps.
`filter_snapshot(snapshot)` returns a `FilterReport` with `analyzable_paths`,
`analyzable_bytes`, and every exclusion. `extra_excluded_directories` and
`extra_excluded_suffixes` add rules without subclassing.

`AnalysisService(file_filter=...)` consumes the port, so excluded files are
never read or handed to a `LanguageAnalyzer`; they are reported in
`RepositoryAnalysis.skipped_paths`, which is also what the graph store's
`excluded_count` records. `analyze_repository` also enforces the repository
caps through the port as it walks, so an oversized checkout raises
`RepositoryTooLargeError` instead of being analyzed in full. The default
service uses `SourceFileFilter()`.

```python
from repolens.analysis import AnalysisService
from repolens.ingestion import ArchiveLimits, SourceFileFilter

file_filter = SourceFileFilter(ArchiveLimits(max_file_bytes=512 * 1024))
report = file_filter.filter_snapshot(snapshot)
# FilterReport(analyzable_paths=('app/main.py', ...), exclusions=(...))

analysis = AnalysisService(file_filter=file_filter).analyze_repository(snapshot.root)
```

The mini repository used by the filter tests is
`tests/fixtures/filter_mini_repo/`; its README lists the cases it covers.

## Source Analysis (`repolens.analysis`)

`repolens.analysis` reads a repository tree and reports the imports and
top-level symbols of every file it can analyze. Source is parsed with the
standard library `ast` module only; analyzed files are never imported,
executed, or evaluated.

### LanguageAnalyzer

`repolens.analysis.ports.LanguageAnalyzer` is the per-language interface:
`language`, `file_extensions`, `supports(path)`, and
`analyze(path, source) -> ParsedFile`. `PythonAnalyzer` implements it for
`.py` and `.pyi` files. `AnalysisService` picks an analyzer by file path, so
adding a second language means registering another analyzer
(`AnalysisService((PythonAnalyzer(), TypeScriptAnalyzer()))`) rather than
changing the service, the graph store, or search.

### Reported Data
- **`ParsedFile`**: `path` (POSIX, relative to the repository root),
  `language`, `parsed`, `line_count`, `imports`, `symbols`, and an `error`
  when the file did not parse.
- **`ParsedImport`**: `module`, `form` (`import` or `from`), `level` (0 for an
  absolute import, otherwise the relative-import depth), the `symbols` taken
  from the module (`'*'` for a star import), and the `line` of the first
  import of that module. `raw_name` renders the reference as written, such as
  `os.path` or `..config`. Imports inside functions and classes are reported
  too, and repeated imports of one module are merged into a single record.
- **`ParsedSymbol`**: `name`, `kind` (`function`, `class`, or `variable`), and
  `line`. Only module-level declarations are reported; methods and nested
  definitions belong to their enclosing symbol. Declarations guarded by
  module-level control flow bind module-level names, so an `if TYPE_CHECKING:`
  class, a `try`/`except ImportError` fallback, and a platform- or
  version-gated definition are all reported, each once at the line of its
  first branch.
- **`RepositoryAnalysis`**: every analyzed `ParsedFile` sorted by path, plus
  `skipped_paths` for files no registered analyzer supports.

A file with a syntax error, invalid UTF-8, or a read error is reported with
`parsed=False` and a `ParseError` instead of raising, so one bad file never
hides the rest of the repository. Tree walks skip `.git`, `.hg`, `.svn`, and
`__pycache__`, and do not follow symlinks; the full exclusion rules (vendored
code, generated files, size limits) belong to the ingestion filter.

`repolens.analysis.adapter` maps results onto the graph store's records:
`to_analyzed_file`, `to_analyzed_files`, and `to_analysis_counts`. Imports are
stored with their written name and the `unresolved` kind, because deciding
whether a name points at another file in the repository or at an external
package needs the whole file list; the import classifier assigns the final
`internal` or `external` kind and target path.

Each `ImportRecord` also carries the imported names and the relative-import
depth (`symbols` and `level`). `raw_name` renders a reference as written, so
by itself it collapses `from . import config` to `"."` and
`from app.services import billing` to `"app.services"` — neither of which
tells the classifier to resolve `app/config.py` or
`app/services/billing.py`. Keeping the names also preserves the ambiguity the
classifier has to settle: `billing` may be the `app/services/billing.py`
module or a name re-exported by `app/services/__init__.py`. These two fields
hand parsing off to classifying in memory; the pipeline classifies before it
stores, so the `imports` table persists only the resolved kind and target.

### Import Classification

`repolens.analysis.classify_imports` is the classifying stage: it takes the
storable records the adapter produced and returns them with every import
labeled `internal`, `external`, or `unresolved`, and with the `target_path` or
`target_package` that label refers to. It works on the whole file list,
because resolving one import needs to know every file the repository
contains, and it runs before storing, so no schema change is involved.
`ImportClassifier` is the object behind it, for a caller that already has the
repository's file paths.

Resolution follows Python's module layout — dotted names, `__init__.py`
packages, `.pyi` stubs — over the analyzed paths only. Nothing is imported,
executed, or looked up on `sys.path`, and only the analyzed files can be a
target, since they are the only files the store can point an import at.

- **Source roots.** Absolute imports resolve against the repository root and
  against any directory that is not itself inside a package, so a `src/` or
  `backend/` layout resolves `app.config` to `src/app/config.py` instead of
  reporting an external `app` package. The roots that contain the importing
  file are tried first, deepest first, the way the nearest directory on
  `sys.path` wins at runtime; the roots outside its tree follow, so a
  `tests/` file still reaches a `src/` package the way an installed
  distribution would.
- **The owning root is a boundary.** The search stops at the first containing
  root that holds the top-level package being imported, including as a
  namespace directory. Two checkouts of one package in a monorepo therefore
  stay apart: `import app.only_a` from `service_b/app/main.py` is
  `unresolved`, not an edge into `service_a/app/only_a.py` that Python would
  never take.
- **Relative imports** resolve against the importing file's package: level 1
  is its own package and each further level is one package up, so
  `from .. import config` in `app/services/billing.py` resolves to
  `app/config.py`, and `from . import config` in `app/__init__.py` resolves to
  the sibling `app/config.py`. A level that reaches past the repository root
  is `unresolved`; a relative import is never external.
- **The dotted module resolves first**, because only a package can hold
  submodules. The trailing name in `from app.config import DEFAULT_TIMEOUT`
  is therefore an attribute and the import resolves to `app/config.py`, even
  where a directory happens to hold an `app/config/DEFAULT_TIMEOUT.py`: a
  file module can never load a submodule.
- **Imported names are tried as submodules** when the module is a package, or
  a directory with no module file of its own (a namespace package, which
  includes the empty module of `from . import config`). One statement can
  reach several files, so every resolved submodule gets its own record and
  its own edge: `from pkg import a, b` links to `pkg/a.py` and `pkg/b.py`,
  and `from app.services import billing` links to `app/services/billing.py`
  rather than the `app/services/__init__.py` that may re-export it — an edge
  to the file that defines the code says more than an edge to the package
  that forwards it. The module itself is reported as well unless every
  imported name turned out to be a submodule, so
  `from app.services import billing, InvoiceCalculator` links to both the
  submodule and the package that defines the other name.
- **An absolute import of a missing module falls back to its closest parent
  package**, because `import pkg.generated.models` runs `pkg/__init__.py`
  whether or not the named module is in the analysis — which is what happens
  when the ingestion filter excluded it. The nearest package that *is* in the
  analysis is the most precise true target for that dependency.
- **Repeated references to one target are merged** per file, so a file that
  reaches `app/services/billing.py` both as
  `from app.services import billing` and as
  `from app.services.billing import InvoiceCalculator` keeps one record and
  one edge.
- **Star imports** are resolved from their module alone, never from their
  names: `'*'` is never treated as a submodule, so `from .services import *`
  is an internal edge to `app/services/__init__.py`, `from numpy import *` is
  external, and `from app.plugins import *` with no such module stays
  `unresolved`.
- **External** is the fallback for an absolute import the repository does not
  contain, and `target_package` is its top-level name, so `os.path` reports
  `os`. When that top-level name *is* in the repository but neither the named
  module nor any parent package of it is, the import is `unresolved` rather
  than a third-party dependency.
- **A file never depends on itself**: a reference that resolves back to the
  importing file is `unresolved`, so `from . import missing` in a package's
  `__init__.py` does not become a self edge.

A file that did not parse reports no imports, so it passes through
classification unchanged — and it is still a resolvable target for the
imports in other files, because it is a repository file all the same.

```python
from repolens.analysis import (
    AnalysisService,
    classify_imports,
    to_analysis_counts,
    to_analyzed_files,
)
from repolens.graph import AnalysisRecord, SqliteGraphStore

analysis = AnalysisService().analyze_repository("/tmp/checkout")
for file in analysis.files:
    print(file.path, [i.raw_name for i in file.imports], [s.name for s in file.symbols])

classified = classify_imports(to_analyzed_files(analysis))
for file in classified:
    print(file.path, [(i.raw_name, i.kind, i.target_path) for i in file.imports])

SqliteGraphStore("repolens.db").save(
    AnalysisRecord(
        analysis_id="analysis-1",
        repo="https://github.com/owner/repo",
        sha="0123456789abcdef0123456789abcdef01234567",
        counts=to_analysis_counts(analysis),
        files=classified,
    )
)
```

The mini repository used by the analyzer tests is
`tests/fixtures/analysis_mini_repo/`; its README lists the cases it covers.

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
- `POST /analyses` — Validates the GitHub URL, resolves the ref to a commit SHA, reuses a non-expired cached analysis for `(repo, sha)` or starts a new analysis, returning `{analysisId, sha, status}`.
- `GET /analyses/{analysis_id}` — Returns lifecycle status, active stage, summary counts, cache flag, ISO-8601 timestamps, and any structured error.
- `DELETE /analyses/{analysis_id}` — Cancels a queued or running analysis (`204 No Content`).
- `GET /analyses/{analysis_id}/graph` — Returns `{modules, files, edges}` for the interactive dependency map (`repolens.graph.endpoints`).
- `GET /analyses/{analysis_id}/files/{file_path:path}` — Returns `{path, module, parsed, lineCount, symbols, imports, importedBy, sourceUrl}` with pinned GitHub blob and `#L<line>` URLs.
- `GET /analyses/{analysis_id}/search` — Queries `SearchService(store)` and returns ranked files with 1-based reading-order `position` and match line numbers.

Run the main backend server locally from the repository root:

```bash
PYTHONPATH=backend python3 -m uvicorn repolens.api.app:app --app-dir backend --reload
```

The server keeps analyses in an in-memory SQLite database, so restarting it
clears them. Set `GITHUB_TOKEN` to raise GitHub's anonymous API limit of 60
requests an hour; the token is only sent to `api.github.com`.

## Analysis Pipeline (`repolens.pipeline`)

`repolens.api.app:app` starts analyses with `PipelineAnalysisRunner`.
`create_app()` without a runner keeps `DefaultAnalysisRunner`, an offline stub
whose analyses stay queued, for contract tests.

`POST /analyses` resolves the ref (or the default branch) to a commit SHA with
`repolens.ingestion.GitHubRefResolver` before it answers, so the response
names the SHA and a completed, unexpired analysis of the same commit is
reused. Resolution failures are returned directly: `REPO_NOT_FOUND`,
`REF_NOT_FOUND`, `REPO_EMPTY`, `RATE_LIMITED`, or `GITHUB_UNAVAILABLE`.

### Caching

Analyses are cached by `(repo, sha)` for 24 hours from when they were first
run:

- A second `POST /analyses` for the same repository and commit returns the
  existing `analysisId` without downloading or parsing again, and that
  analysis then reports `fromCache: true`. Reuse does not extend its expiry.
- Until it is deleted, an expired analysis answers `410 ANALYSIS_EXPIRED` on
  every endpoint, and is never reused.
- Every `POST /analyses` first deletes expired analyses with
  `SqliteGraphStore.evict_expired()`, so the next request for that commit
  analyzes it again and the old ID answers `404 ANALYSIS_NOT_FOUND`.

The remaining stages run on a background thread and are recorded on the
analysis, which is what the frontend shows while it polls
`GET /analyses/{id}`:

1. **downloading**: `GitHubSource` downloads and extracts the archive into a
   temporary directory, deleted once the analysis finishes.
2. **filtering**: fails with `NO_PYTHON_FILES` if no file has an analyzer.
3. **parsing**: `AnalysisService` parses every supported file.
4. **classifying**: `classify_imports` resolves each import against the file
   list (see below).
5. **storing**: the graph is saved and the analysis marked `completed`.

A cancel (`DELETE /analyses/{id}`) stops the pipeline at the next stage and is
never overwritten by a later result. An ingestion error fails the analysis
with its own code; anything unexpected is logged and reported as
`ANALYSIS_FAILED`.

### Import Classification

The classifying stage is `repolens.analysis.classify_imports`: it marks each
import `internal`, `external`, or `unresolved`, and resolves the internal ones
to the file they reach. Its rules are documented under
[Import Classification](#import-classification) in Source Analysis above.

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

## Search Precision Measurement (`benchmarks`)

`benchmarks/search_precision.py` answers Risk 1 -- does RepoLens search beat
grep? -- on 19 hand-labeled queries over three fixture repositories
(`labeled_queries.json`), and compares top-5 precision with a grep filename
baseline. RepoLens is measured through its production path: parse, classify,
store, then search the store, so the measurement sees the documents the API
serves rather than a hand-written index.

```bash
python -m benchmarks.search_precision            # print the comparison table
python -m benchmarks.search_precision --write    # refresh measured_precision.json
```

Measured top-5 precision, overall: **RepoLens 0.211, grep 0.042**, against an
ideal ceiling of 0.326 for these labels. `tests/test_search_precision.py`
checks the labels and reproduces the run against the recorded numbers in
`benchmarks/measured_precision.json`. `benchmarks/README.md` has the
per-repository table, the labeling rule, and what the misses show.

## Import Classification Measurement (`benchmarks`)

`benchmarks/import_classification.py` answers Risk 2 -- do resolved imports
point where Python points? -- by scoring `classify_imports` against 85
hand-labeled references across seven layouts in
`tests/fixtures/import_classification/` (src layout, namespace packages,
re-exports, relative imports, a module colliding with a same-named directory,
monorepo source roots, and stdlib/third-party packages). The labels were
written from Python's import rules and checked against `importlib`, not taken
from RepoLens' output.

```bash
python -m benchmarks.import_classification            # print the table
python -m benchmarks.import_classification --write    # refresh the record
```

Measured overall: **84 of 85 correct (98.8%), 3 unresolved (3.5%)**, against 4
references that should be unresolved. The one miss is real and left failing:
`import app.config.defaults` is a `ModuleNotFoundError` where `app/config.py`
shadows `app/config/`, and the classifier reports an internal edge instead.
`tests/test_import_classification.py` reproduces the run against
`benchmarks/measured_classification.json`, and the fixture README has the
per-layout table, the labeling rules, and what each layout covers.

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
runs the suite on Python 3.11, 3.12, and 3.13 for every pull request that
touches `backend/`.

### End-to-end test

`tests/test_e2e_reference_repo.py` (marked `e2e`) runs the whole pipeline on
the hand-written reference repository in `tests/fixtures/e2e_reference/` through
the HTTP API, with only GitHub's network transport faked. It compares the
summary, graph, every file's symbols and imports, and the reading order of
several searches with the hand-written `expected.json`, so drift between
ingestion, analysis, the graph store, and search fails CI. CI runs it as its own
"End-to-end (reference repo)" job; the matrix job skips it with
`-m "not e2e"`. Locally, `python -m pytest` runs everything and
`python -m pytest -m e2e` runs only this test. The fixture's README lists the
cases it covers and how to update the expectations.

# Backend

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

The production GraphStore adapter should implement the `SearchIndex`
protocol by returning `SearchDocument` records for exactly the requested
analysis ID, and raise `AnalysisUnavailableError` when that analysis is
missing or expired. Only that adapter should know database-specific schemas.
The API host supplies its configured service:

```python
from fastapi import FastAPI
from repolens.api.search import install_search_api
from repolens.search import SearchService

app = FastAPI()
install_search_api(app, SearchService(graph_search_index))
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

The production GraphStore adapter and the main application/analysis routes are
separate team components. When available, wire the production `SearchIndex`
into `SearchService`, then mount it with `install_search_api`; the fixture
adapter can be removed from the runtime demo without changing either service.

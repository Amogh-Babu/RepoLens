# RepoLens

RepoLens is a web-based code exploration platform designed to help developers onboard onto unfamiliar GitHub repositories. By pairing interactive dependency graphs with feature-centric reading recommendations, RepoLens enables developers to quickly locate entry points, trace code workflows, and understand file relationships without manually sifting through complex directory structures.

---

## Goals

* Help onboarding developers locate entry points for specific features without deciphering unfamiliar repository directory trees.
* Generate clear dependency graphs from static code analysis to visualize how relevant files and modules connect.
* Recommend a reading order for related files based on symbol definitions and import relationships.
* Deliver an interactive web tool that parses public Python repositories safely without executing untrusted code.

---

## Repository Layout

```text
├── frontend/          # Web user interface (React 19, TypeScript, Vite, React Flow, Vitest)
├── backend/           # API server, GitHub ingestion, AST analysis, graph store, and search (Python / FastAPI / SQLite)
├── docs/              # Living document snapshots, specifications, and architecture diagrams
├── .github/           # Issue templates, PR templates, and GitHub Actions CI/CD workflows
├── Dockerfile         # The whole app (frontend + backend) in one pinned image
├── compose.yaml       # `docker compose up` runs it on http://localhost:8000
├── .python-version    # The Python version the image and CI use (3.12)
├── .nvmrc             # The Node.js version the image and CI use (22)
├── Makefile           # Optional shortcuts for developers on macOS/Linux
└── README.md          # Project overview and instructions for building, testing, and running
```

---

## Run RepoLens (Docker, one command)

The only thing you need installed is **Docker** (Docker Desktop on macOS and
Windows, or Docker Engine with the Compose plugin on Linux). You do not need
Python, Node.js, `make`, or a virtual environment: the image carries its own
pinned versions of everything.

From the repository root:

```bash
docker compose up --build
```

Then open **http://localhost:8000**. The first build takes a few minutes; later
starts take seconds. Analyses are kept in a Docker volume, so they survive
restarts until they expire after 24 hours. Press `Ctrl+C` to stop.

* To use the image published by CI instead of building it:
  `docker compose pull && docker compose up`.
* Optional: set `GITHUB_TOKEN` in your shell before starting to raise GitHub's
  API limit of 60 requests an hour (`GITHUB_TOKEN=... docker compose up`).
* The API and its health check live under `/api` (for example
  `http://localhost:8000/api/health`).

The Docker image includes the 67 MB local search model. A development server
downloads it the first time an analysis is indexed; set
`REPOLENS_EMBEDDING_CACHE` to choose where those model files are stored.

### Using RepoLens in the Browser

1. Open **http://localhost:8000** (or **http://localhost:5173** when running the development servers below).
2. Paste any public Python GitHub repository URL (for example, `https://github.com/pallets/itsdangerous` or `https://github.com/pallets/click`) and optionally specify a branch, tag, or commit SHA.
3. Click **Analyze** to download, filter, parse, and store the repository's dependency graph.
4. Start with a task in the **Search Bar**, in your own words (for example, "where do I start if I'm working on production?"). RepoLens combines exact matches with a local embedding model, then gives you a ranked reading order with explanations. Search runs locally; repository text is not sent to an embedding service.
5. In the reading list, choose whether you want the overall topic, implementation, configuration, or tests and examples. The choice prioritizes files based on their paths without excluding other results. The dependency map can show only search matches, including matches beyond the current reading-list page.

---

## Develop RepoLens

### Prerequisites

* **Python 3.11 or newer.** The pinned version in [`.python-version`](.python-version) (3.12) is what the image and CI use; CI also runs the suite on 3.11 and the newest Python release.
* **[uv](https://docs.astral.sh/uv/getting-started/installation/)** to install the backend's locked dependencies. uv also downloads the pinned Python for you if it is missing, so you do not need `venv` or a system Python.
* **Node.js 22** (see [`.nvmrc`](.nvmrc)) with `npm`.
* `make` is optional; every step below is a plain command.

### Install

```bash
cd backend && uv sync --locked && cd ..
```

```bash
npm --prefix frontend ci
```

`uv sync --locked` creates `backend/.venv` with exactly the versions in
[`backend/uv.lock`](backend/uv.lock). Without uv,
`python -m pip install -r backend/requirements-dev.txt` installs the same
pinned versions (the file is exported from the lockfile and checked in CI).

### Run the Development Servers

Run the backend and the frontend in two terminals:

```bash
cd backend && uv run uvicorn repolens.api.app:app --reload --port 8000
```

```bash
npm --prefix frontend run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api/*` to the
backend on port 8000, and the API's interactive docs are at
**http://127.0.0.1:8000/docs**. (On macOS/Linux, `make run` starts both.)

*(To run the frontend against offline mock data without the backend, set
`VITE_API_MODE=mock` in `frontend/.env.local`. See
[`frontend/README.md`](frontend/README.md) and
[`backend/README.md`](backend/README.md) for component-specific options.)*

### Test

| Part | Framework | Command (from the repository root) | Add a test |
| --- | --- | --- | --- |
| **Backend** | `pytest` | `cd backend && uv run pytest` | Add `backend/tests/test_<feature>.py` with `test_*` functions |
| **Frontend** | `Vitest` + React Testing Library | `npm --prefix frontend test` (also `run lint`, `run format:check`, `run typecheck`) | Add `<Component>.test.tsx` or `<module>.test.ts` next to the code under test |
| **Image** | `pytest` inside Docker | `docker build --target test .` | Runs the backend suite in the exact production environment |

### Update Dependencies

Backend dependencies are locked. To upgrade them, move `exclude-newer` in
[`backend/pyproject.toml`](backend/pyproject.toml) to a recent date (keep it a
couple of weeks in the past), then run `uv lock` and re-export the
requirements files:

```bash
cd backend && uv lock && uv export --locked --no-dev --format requirements-txt --no-emit-project -o requirements.txt && uv export --locked --format requirements-txt --no-emit-project -o requirements-dev.txt
```

---

## Operational Use Cases (First Prototype Status)

First-version implementations of all major system components (**React Frontend**, **FastAPI HTTP Layer**, **GitHub Ingestion & File Filtering**, **Python AST Analyzer & Import Classifier**, **SQLite Graph Store**, and **Search & Ranking Service**) are integrated and operational.

> **Prototype Note**: The use cases below represent our **first integrated prototype** and are still being refined, benchmarked, and evaluated. Some edge cases and interactions are not yet finalized and may be subject to bugs (see **Current Prototype Limitations & Ongoing Work** below).

### 1. Use Case 1: Analyze a Public Repository by URL and Commit *(Operational — Prototype)*
* **Components Touched**: React Landing Page (`RepoInputForm`) $\rightarrow$ FastAPI (`POST /analyses`, `GET /analyses/{id}`) $\rightarrow$ GitHub Ref Resolver & Archive Fetcher (`repolens.ingestion`) $\rightarrow$ Auto-generated/Vendored File Filter $\rightarrow$ Python AST Parser & Import Classifier (`repolens.analysis`) $\rightarrow$ SQLite Graph Store (`repolens.graph`) $\rightarrow$ Frontend Summary Bar, File Explorer, and Dependency Map.
* **How to Verify**:
  1. Run `docker compose up --build` and open **http://localhost:8000** (or start the development servers and open **http://localhost:5173**).
  2. Enter a public Python repository URL (e.g., `https://github.com/pallets/itsdangerous`) and click **Analyze**.
  3. Observe the pipeline stage indicator (`resolving` $\rightarrow$ `downloading` $\rightarrow$ `filtering` $\rightarrow$ `parsing` $\rightarrow$ `classifying` $\rightarrow$ `indexing` $\rightarrow$ `storing`) and the resulting summary bar (analyzed, excluded, and unparsed file counts), file explorer tree, and module dependency map.

### 2. Use Case 2: Search for a Feature and Get a Ranked Reading List *(Operational — Prototype)*
* **Components Touched**: React Search Bar & Reading List $\rightarrow$ FastAPI (`GET /analyses/{id}/search`) $\rightarrow$ `SearchService` (`repolens.search`) querying `SqliteGraphStore` (`SearchIndex`) $\rightarrow$ DependencyMap search highlighting.
* **How to Verify**:
  1. After Use Case 1 completes, describe a task in the search bar (e.g., "where do I check if a signature expired" or "where do I start with production").
  2. The backend combines keyword matches in filenames, symbols, members, imports and prose with local BGE-small semantic similarity. It returns matching evidence, explains semantic matches, and orders exact-match dependencies before their callers while highlighting results on the map.

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

---

## Continuous Integration and Delivery

GitHub Actions workflows live in [`.github/workflows/`](.github/workflows/):

* [`backend.yml`](.github/workflows/backend.yml) checks that `backend/uv.lock` and the exported requirements files are current, runs `pytest` on the pinned Python from `.python-version` with the locked dependencies, runs a compatibility job on Python 3.11 (the minimum) and the newest Python release, and runs a dedicated end-to-end job that runs the full pipeline on a hand-written reference repository and compares the results against expected output.
* [`frontend.yml`](.github/workflows/frontend.yml) runs ESLint, Prettier, the TypeScript typecheck, Vitest, and the production build on the Node version in `.nvmrc`.
* [`release.yml`](.github/workflows/release.yml) builds the Docker image, runs the backend suite inside it, starts the container and smoke-tests the UI and API, and on `main` publishes it to `ghcr.io/amogh-babu/repolens` (`:latest` and the commit SHA). If the repository has a `DEPLOY_HOOK_URL` secret (for example a Render deploy hook), it then redeploys the hosted demo.

The backend and frontend workflows run on pull requests and on pushes to `main` that modify their part of the repository; the release workflow runs on every push to `main` and on pull requests that change the image. All of them can also be started from the Actions tab (**Run workflow**).

---

## Documentation & Links

* **Living Document**: [RepoLens Requirements Specification (Google Docs)](https://docs.google.com/document/d/1ZTgu6tfoWwx9FWWS-5DqG5CtgXJ-zucDNXEEca_Qy4s/edit?tab=t.sql8ybk4ej5d#heading=h.18mw63g8e8ay) | [Snapshot in `docs/`](docs/LivingDoc.md)
* **Issue Tracker**: [GitHub Issues](https://github.com/Amogh-Babu/RepoLens/issues)
* **Coding Guidelines**: [`coding-guidelines.md`](coding-guidelines.md)
* **Component Docs**: [`backend/README.md`](backend/README.md) | [`frontend/README.md`](frontend/README.md)

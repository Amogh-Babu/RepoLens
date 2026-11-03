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
├── .github/           # Issue templates, PR templates, and GitHub Actions CI workflows
├── Makefile           # Automated one-command setup, build, test, and run targets
└── README.md          # Project overview and instructions for building, testing, and running
```

---

## Prerequisites

* **Python**: `3.11` or newer (tested on Python 3.11, 3.12, and 3.13)
* **Node.js**: `22` or newer (includes `npm`)
* **Make**: GNU Make (standard on macOS and Linux; Windows users can run the manual commands listed below or use WSL)

---

## How to Build the System

### Automated Build (One Command)

From the repository root, run:

```bash
make build
```

This command automatically:
1. Creates a Python virtual environment at `.venv/` (if not already present).
2. Installs backend runtime and test dependencies from [`backend/requirements-dev.txt`](backend/requirements-dev.txt).
3. Installs frontend dependencies cleanly via `npm --prefix frontend ci`.
4. Verifies backend Python compilation and builds the production frontend bundle (`tsc -b && vite build`) into `frontend/dist/`.

### Manual Build Steps (Without `make`)

```bash
# 1. Backend setup
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt

# 2. Frontend setup & production build
cd frontend
npm ci
npm run build
cd ..
```

---

## How to Test the System

### Automated Test Suite (One Command)

After running `make build` (or `make setup`), run the entire backend and frontend verification suite from the repository root:

```bash
make test
```

`make test` runs:
* **Backend (`make test-backend`)**: `pytest` across all unit, integration, and end-to-end reference repository tests in `backend/tests/`.
* **Frontend (`make test-frontend`)**: ESLint (`npm run lint`), Prettier formatting check (`npm run format:check`), TypeScript compiler check (`npm run typecheck`), and the Vitest unit/component test suite (`npm test`).

### Running Individual Test Suites

| Part | Framework | Automated (`make`) | Manual command (from repo root) | Add a test |
| --- | --- | --- | --- | --- |
| **Backend** | `pytest` | `make test-backend` | `.venv/bin/pytest -c backend/pyproject.toml backend/tests` | Add `backend/tests/test_<feature>.py` with `test_*` functions |
| **Frontend** | `Vitest` + React Testing Library | `make test-frontend` | `cd frontend && npm test` | Add `<Component>.test.tsx` or `<module>.test.ts` next to the code under test |

---

## How to Run the System

### Option 1: Single-Command Full-Stack Launch (`make run`)

From the repository root (after `make build` or `make setup`), start both the FastAPI backend and the Vite frontend dev server together:

```bash
make run
```

* **Frontend UI**: Open **http://localhost:5173** in your browser.
* **Backend API & OpenAPI Docs**: Running at **http://127.0.0.1:8000** (interactive Swagger UI at **http://127.0.0.1:8000/docs**).
* The Vite dev server automatically proxies `/api/*` requests to `http://127.0.0.1:8000`.
* Press `Ctrl+C` to stop both servers cleanly.

### Option 2: Run Backend and Frontend in Separate Terminals

**Terminal 1 — Start the FastAPI Backend (`http://127.0.0.1:8000`):**

```bash
make run-backend
# Or manually:
PYTHONPATH=backend .venv/bin/uvicorn repolens.api.app:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Start the React Frontend (`http://localhost:5173`):**

```bash
make run-frontend
# Or manually:
cd frontend && npm run dev
```

### Using RepoLens in the Browser

1. Open **http://localhost:5173**.
2. Paste any public Python GitHub repository URL (for example, `https://github.com/pallets/itsdangerous` or `https://github.com/pallets/click`) and optionally specify a branch, tag, or commit SHA.
3. Click **Analyze** to download, filter, parse, and store the repository's dependency graph.
4. Explore the **File Explorer**, click module groups on the **Interactive Dependency Map** to inspect file relationships and open pinned GitHub source links, or enter a feature keyword in the **Search Bar** to get a ranked reading order with explanations.

*(Optional: To run the frontend against offline mock fixture data without starting the backend, set `VITE_API_MODE=mock` in `frontend/.env.local`. See [`frontend/README.md`](frontend/README.md) and [`backend/README.md`](backend/README.md) for component-specific options.)*

---

## Operational Use Cases (First Prototype Status)

First-version implementations of all major system components (**React Frontend**, **FastAPI HTTP Layer**, **GitHub Ingestion & File Filtering**, **Python AST Analyzer & Import Classifier**, **SQLite Graph Store**, and **Search & Ranking Service**) are integrated and operational.

> **Prototype Note**: The use cases below represent our **first integrated prototype** and are still being refined, benchmarked, and evaluated. Some edge cases and interactions are not yet finalized and may be subject to bugs (see **Current Prototype Limitations & Ongoing Work** below).

### 1. Use Case 1: Analyze a Public Repository by URL and Commit *(Operational — Prototype)*
* **Components Touched**: React Landing Page (`RepoInputForm`) $\rightarrow$ FastAPI (`POST /analyses`, `GET /analyses/{id}`) $\rightarrow$ GitHub Ref Resolver & Archive Fetcher (`repolens.ingestion`) $\rightarrow$ Auto-generated/Vendored File Filter $\rightarrow$ Python AST Parser & Import Classifier (`repolens.analysis`) $\rightarrow$ SQLite Graph Store (`repolens.graph`) $\rightarrow$ Frontend Summary Bar, File Explorer, and Dependency Map.
* **How to Verify**:
  1. Run `make run` and open **http://localhost:5173**.
  2. Enter a public Python repository URL (e.g., `https://github.com/pallets/itsdangerous`) and click **Analyze**.
  3. Observe the pipeline stage indicator (`resolving` $\rightarrow$ `downloading` $\rightarrow$ `filtering` $\rightarrow$ `parsing` $\rightarrow$ `classifying` $\rightarrow$ `storing`) and the resulting summary bar (analyzed, excluded, and unparsed file counts), file explorer tree, and module dependency map.

### 2. Use Case 2: Search for a Feature and Get a Ranked Reading List *(Operational — Prototype)*
* **Components Touched**: React Search Bar & Reading List $\rightarrow$ FastAPI (`GET /analyses/{id}/search`) $\rightarrow$ `SearchService` (`repolens.search`) querying `SqliteGraphStore` (`SearchIndex`) $\rightarrow$ DependencyMap search highlighting.
* **How to Verify**:
  1. After Use Case 1 completes, type a feature keyword (e.g., `signer`, `serializer`, or `timed` for `pallets/itsdangerous`) into the search bar and submit.
  2. The backend matches filenames, symbols, imports, and comments, orders matched dependencies ahead of callers, and returns a ranked reading list with one-line explanations and expandable match evidence while highlighting matching files on the map.

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

## Continuous Integration

GitHub Actions runs both suites automatically via workflows in [`.github/workflows/`](.github/workflows/):

* [`backend.yml`](.github/workflows/backend.yml) runs `pytest` on Python 3.11, 3.12, and 3.13, plus a dedicated end-to-end job that runs the full pipeline on a hand-written reference repository and compares the results against expected output.
* [`frontend.yml`](.github/workflows/frontend.yml) runs ESLint, Prettier, the TypeScript typecheck, Vitest, and the production build on Node 22.

Each workflow runs automatically on pull requests and on pushes to `main` that modify its part of the repository, and can also be triggered manually from the GitHub Actions tab (**Run workflow**).

---

## Documentation & Links

* **Living Document**: [RepoLens Requirements Specification (Google Docs)](https://docs.google.com/document/d/1ZTgu6tfoWwx9FWWS-5DqG5CtgXJ-zucDNXEEca_Qy4s/edit?tab=t.sql8ybk4ej5d#heading=h.18mw63g8e8ay) | [Snapshot in `docs/`](docs/RepoLens%20-%20CSE%20403.md)
* **Issue Tracker**: [GitHub Issues](https://github.com/Amogh-Babu/RepoLens/issues)
* **Coding Guidelines**: [`coding-guidelines.md`](coding-guidelines.md)
* **Component Docs**: [`backend/README.md`](backend/README.md) | [`frontend/README.md`](frontend/README.md)

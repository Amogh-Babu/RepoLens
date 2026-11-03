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

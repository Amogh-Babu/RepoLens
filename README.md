# RepoLens

RepoLens is a web-based code exploration tool that helps onboarding developers get oriented in an unfamiliar codebase.

Given a public GitHub repository and a branch, tag, or commit, RepoLens statically analyzes the source, graphs file and module dependencies on an interactive map, and lists files related to a specific feature. You can quickly find entry points, trace code workflows, and understand file relationships without manually sifting through the directories.

RepoLens does not import, execute, or build code from analyzed repositories.

## Try RepoLens

Once RepoLens releases, you'll be able to access the tool online.

### Run locally with Docker

You can also run RepoLens locally with [Docker](https://docker.com). This means you don't need Python, Node.js, `make`, or a virtual environment. Depending on your operating system, you just need:

- **Windows, macOS:** Docker Desktop
- **Linux:** Docker Engine with the Docker Compose plugin

Next, from the repository root, run:

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

To run an image already published to GitHub Container Registry instead of building locally, run:

```bash
docker compose pull && docker compose up
```

Analyses are kept in a Docker volume and expire after 24 hours. To raise GitHub's anonymous API rate limit, you can set a personal token in your shell before starting RepoLens:

```bash
GITHUB_TOKEN=your_token_here docker compose up
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
* **Semantic Indexing Time**: Embedding files for semantic search is the slowest step. Measured on a 12-core CPU, it takes about 0.3 seconds per file for typical project code and about 0.5 seconds per file for docstring-heavy code (Python standard library). A repository near the 1,000-file cap therefore spends roughly 5 to 8 minutes indexing, over the 3-minute target. If the embedding model cannot load, the analysis still completes and search uses keywords only.
* **Search Ranking Calibration**: Field weights and dependency tie-breaking heuristics are functional but still undergoing precision evaluation and tuning against hand-labeled queries.
* **Synchronous Pipeline Execution**: Analysis currently runs within the request lifecycle; concurrent request deduplication and background progress streaming are still being refined.

Open **http://localhost:8000** (or **http://localhost:5173** when running the development servers below).

In the web application, paste a GitHub repository URL (for example, https://github.com/pallets/click). Optionally, you can choose a branch, tag, or commit SHA. Then press **Analyze**. When analysis is finished, there will be a summary, file explorer, and interactive dependency map.

You can search for a task, feature, or question, like "serializer" or "where is a signature checked?". RepoLens will search file paths, module-level symbols, class members, imports, docstrings, and comments. You'll get a ranked reading list with a short explanation and the reasoning behind each result.

Search results are reflected on the map. Selecting a file highlights its direct dependencies and dependents, helping you explore and narrow a large repository down to the code relevant to your task.

To inspect a file, select it to open its detail panel. You'll see the file path and module, parsed symbols, imports, and files that import it. Press **Open Source on GitHub** to open the file at the exact commit you're analyzing. Symbol links will point you to the corresponding line.

## Contributing

Interested in improving RepoLens?

- Start with [docs/DEVELOPERS.md](https://github.com/Amogh-Babu/RepoLens/tree/main/docs/DEVELOPERS.md) for architecture, setup, tests, benchmarks, and guidance for extending the analyzer.
- Discuss bugs and proposed changes at the [issue tracker](https://github.com/Amogh-Babu/RepoLens/issues).

## Reporting Issues
 
Found a bug or have an idea for RepoLens? Open an issue on the [issue tracker](../../issues) and include the details below. Clear reports help us fix problems faster.
 
### Issue Template
 
Copy this into a new issue and fill in each section:
 
```markdown
**Summary**
A one-sentence description of the problem or request.
 
**Type**
Bug / Feature request / Question / Documentation
 
**Steps to reproduce** (for bugs)
1.
2.
3.
 
**Expected behavior**
What you expected to happen.
 
**Actual behavior**
What actually happened, including any error messages.
 
**Repository analyzed** (if relevant)
A link to the public Python repository, and the branch, tag, or commit if you used one.
 
**Environment**
- OS:
- Docker version:
- Browser:
 
**Screenshots or logs** (optional)
```
 

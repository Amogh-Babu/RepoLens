# Frontend

The RepoLens web client: a React + TypeScript app built with Vite. It shows the
file explorer, the interactive dependency map, the search bar and reading list,
and links to source on GitHub. It holds only UI state; all analysis comes from
the backend REST API.

## Requirements

- Node.js 22 or newer (CI uses Node 22)
- npm (comes with Node)

## Setup

From the repository root:

```bash
cd frontend
npm install
```

## Commands

Run these from `frontend/`.

| Command                | What it does                                       |
| ---------------------- | -------------------------------------------------- |
| `npm run dev`          | Start the dev server at http://localhost:5173      |
| `npm run build`        | Typecheck, then build for production into `dist/`  |
| `npm run preview`      | Serve the production build locally                 |
| `npm run typecheck`    | Run the TypeScript compiler without emitting files |
| `npm run lint`         | Run ESLint                                         |
| `npm run lint:fix`     | Run ESLint and fix what it can                     |
| `npm run format`       | Format every file with Prettier                    |
| `npm run format:check` | Check formatting without changing files            |
| `npm test`             | Run the tests once with Vitest                     |
| `npm run test:watch`   | Run the tests in watch mode                        |

## Project layout

```text
frontend/
├── public/           static files served as-is
├── src/
│   ├── api/          typed REST client for the backend
│   ├── state/        app state (analysis, selection, search)
│   ├── components/   UI pieces
│   ├── pages/        landing page and analysis page
│   ├── test/         test setup
│   ├── App.tsx       routes
│   └── main.tsx      entry point
├── .env.example      environment variables (copy to .env.local)
├── eslint.config.js
├── .prettierrc.json
└── vite.config.ts    Vite and Vitest config, dev server proxy
```

Tests live next to the code they test, named `*.test.ts` or `*.test.tsx`.

## Backend API

All backend calls go through the `ApiClient` interface in
[`src/api/client.ts`](src/api/client.ts). Response types are in
[`src/api/types.ts`](src/api/types.ts) and error codes in
[`src/api/errors.ts`](src/api/errors.ts). Every method rejects only with
`ApiError` (`code`, `message`, `hint`), including network failures
(`NETWORK_ERROR`), timeouts (`TIMEOUT`, 5 s for search and 10 s for
everything else) and cancels (`ABORTED`).

There are two implementations, chosen by `VITE_API_MODE`:

| Mode             | Client          | Use it for                                            |
| ---------------- | --------------- | ----------------------------------------------------- |
| `mock` (default) | `MockApiClient` | Building the UI without a backend                     |
| `http`           | `HttpApiClient` | Talking to the FastAPI backend at `VITE_API_BASE_URL` |

To use the real backend, create `frontend/.env.local`:

```bash
VITE_API_MODE=http
VITE_API_BASE_URL=/api
API_PROXY_TARGET=http://localhost:8000
```

The dev server forwards `/api/...` to `API_PROXY_TARGET` with the `/api`
prefix removed, so the browser never makes a cross-origin request.

### Mock data

The mock client serves a small hand-written Flask app with a login feature
([`src/api/mock/fixtureRepo.ts`](src/api/mock/fixtureRepo.ts)) under any
`https://github.com/<owner>/<repo>` URL. Each pipeline stage takes about
0.6 s. These repository names trigger the error paths from the use cases:

| Repository name | Result                                              |
| --------------- | --------------------------------------------------- |
| `private-repo`  | `REPO_NOT_FOUND` when starting                      |
| `rate-limited`  | `RATE_LIMITED` when starting                        |
| `empty-repo`    | Fails while downloading with `REPO_EMPTY`           |
| `no-python`     | Fails while filtering with `NO_PYTHON_FILES`        |
| `huge-repo`     | Fails while filtering with `TOO_MANY_FILES`         |
| `crash`         | Fails while parsing with `ANALYSIS_FAILED`          |
| `cached`        | Completes immediately, marked as from the cache     |
| `expired-repo`  | Completes, then every request is `ANALYSIS_EXPIRED` |
| `expires-soon`  | Completes, then expires 20 seconds later            |

A ref named `missing-ref` fails with `REF_NOT_FOUND`.

## Routes

| Path                    | Page                            |
| ----------------------- | ------------------------------- |
| `/`                     | Landing page (repository input) |
| `/analysis/:analysisId` | Results for one analysis        |

## Code style

The frontend follows the
[Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html)
(see [`coding-guidelines.md`](../coding-guidelines.md)). ESLint enforces the
rules it can check: named exports only, `const`/`let` instead of `var`, no
`any`, no non-null assertions, naming conventions and import order. Prettier
handles formatting. Run `npm run lint:fix` and `npm run format` before pushing.

## Continuous integration

`.github/workflows/frontend.yml` runs on every pull request that touches
`frontend/`, and on pushes to `main`. It runs lint, the format check, the
typecheck, the tests and the build. To block merging on failures, mark the
"Lint, typecheck, test, build" check as required in the `main` branch
protection rules.

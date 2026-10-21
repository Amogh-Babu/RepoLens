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
├── eslint.config.js
├── .prettierrc.json
└── vite.config.ts    Vite and Vitest config
```

Tests live next to the code they test, named `*.test.ts` or `*.test.tsx`.

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

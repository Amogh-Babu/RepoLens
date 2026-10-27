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
├── frontend/          # Web user interface (React, dependency graph canvas, file viewer)
├── backend/           # API server, AST ingestion pipeline, and graph resolver (Python / FastAPI)
├── docs/              # Living document snapshots, specifications, and architecture diagrams
├── .github/           # Issue templates, PR templates, and CI/CD workflows
└── README.md          # Project overview and developer onboarding
```

---

## Local Setup Instructions

*TBD*

---

## Testing and Continuous Integration

| Part | Test framework | Run locally | Add a test |
| --- | --- | --- | --- |
| Backend | pytest | `cd backend && python -m pip install -r requirements-dev.txt && python -m pytest` | Add `backend/tests/test_<feature>.py` with `test_*` functions |
| Frontend | Vitest + React Testing Library | `cd frontend && npm ci && npm test` | Add `<Component>.test.tsx` or `<module>.test.ts` next to the code under test |

GitHub Actions runs both suites automatically. The workflows live in
`.github/workflows/`:

* `backend.yml` runs pytest on Python 3.11, 3.12, and 3.13.
* `frontend.yml` runs ESLint, Prettier, the TypeScript typecheck, Vitest, and
  the production build.

Each workflow runs on pull requests and on pushes to `main` that change its
half of the repository, and can be started by hand from the Actions tab
("Run workflow"). See `backend/README.md` and `frontend/README.md` for details.

---

## Living Document

* [RepoLens Requirements Specification (Google Docs)](https://docs.google.com/document/d/1ZTgu6tfoWwx9FWWS-5DqG5CtgXJ-zucDNXEEca_Qy4s/edit?tab=t.sql8ybk4ej5d#heading=h.18mw63g8e8ay)

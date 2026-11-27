# AI File Overview Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate PR #112's safe optional AI-summary stack with current main's single AI File Overview interface.

**Architecture:** Restore the recovered backend/provider/cache/API implementation on current main, resolving graph-store and server changes in favor of both feature sets. Wire the frontend's existing file-overview state to cache-only GET and explicit-action POST methods, with no standalone duplicate summary component.

**Tech Stack:** Python 3.11+ / FastAPI / SQLite / Pydantic / OpenAI SDK seam; React 19 / TypeScript / Vitest.

**Spec:** `docs/superpowers/specs/2026-11-23-ai-file-overview-integration-design.md`

## Global Constraints

- No paid or live model calls.
- GET is cache-only; only explicit POST actions may generate.
- Preserve current main and exclude unmerged PRs #140 and #147.
- Keep PR #112 in draft.

## Review Focus

- Cache miss on GET returns `notGenerated` without invoking the provider.
- Disabled or invalid AI configuration cannot prevent server startup or ordinary file details.
- File/path changes cannot display or overwrite another file's summary.
- Regeneration failures preserve the last cached summary.
- Encoded/nested paths behave identically in real and mock clients.

---

### Task 1: Restore and reconcile the backend foundation

**Files:** recovered `backend/repolens/ai/**`, API/server, graph store/schema, onboarding service, dependency locks, docs, and backend tests.

- [ ] Apply the recovered commit chain onto current main without touching the original branch/worktree.
- [ ] Resolve conflicts so both current graph/search/pipeline improvements and the recovered AI invariants remain.
- [ ] Run focused AI/config/API/store tests and fix regressions test-first.

### Task 2: Integrate the single frontend overview

**Files:** `frontend/src/api/**`, `frontend/src/components/FileDetailPanel*`, owning page/workspace state, and tests.

- [ ] Add failing tests for cached automatic display, explicit generation only, disabled fallback, regeneration, failures, and selection races.
- [ ] Remove the duplicate recovered section and connect the existing overview to status + cache-only GET + explicit POST.
- [ ] Align real client, types, errors, and mock client; run focused tests after each behavior.

### Task 3: Regression and full verification

**Files:** backend/frontend regression tests and documentation as needed.

- [ ] Confirm provider/AST validation/cache/rate-limit/source tests remain offline and green.
- [ ] Run full backend tests and offline reference/integration tests.
- [ ] Run frontend lint, format check, typecheck, full tests, and production build.
- [ ] Confirm diff excludes PR #140/#147-only changes and contains no live-model invocation.
- [ ] Commit the completed integration locally and report the SHA and exact results.

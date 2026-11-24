# AI File Overview Integration Design

## Intent

Finish draft PR #112 on current `main` without losing its verified AI-summary backend, while preserving the simpler AI File Overview that users already see in the file panel.

## Goals and constraints

- Keep one AI File Overview interface; do not restore the duplicate AI File Summary section.
- A file selection may automatically fetch a cached summary, but only an explicit user action may generate or regenerate one.
- `GET` routes are cache-only and must never call a model. Model calls remain behind `POST`.
- Preserve structured output, AST/static-analysis verification, source pinning, SQLite caching, rate/concurrency limits, usage accounting, disabled-AI fallback, and offline test seams.
- Align backend responses, frontend client/types/state, and mock client behavior.
- Preserve current `main` improvements. Do not incorporate unmerged PR #140 or #147.
- Do not make live or paid model calls. Keep PR #112 in draft pending live-model evaluation.

## Approach

Use the recovered PR implementation as the backend and API foundation, resolve it onto current `main`, then adapt the frontend behavior into the existing `FileDetailPanel` overview rather than keeping the recovered standalone `AiSummarySection`. This preserves the most-tested safety boundaries while avoiding parallel interfaces. Reimplementing the provider stack or retaining both UI surfaces would add risk or violate Option 1.

## User-visible behavior

- When AI is disabled, the ordinary static-analysis file panel continues to work without an AI control.
- When AI is enabled, selecting a file performs cache-only reads. A cached verified summary appears automatically.
- If no cached summary exists, the overview offers a Generate action. Generation begins only after that click.
- A cached summary offers an explicit Regenerate action and remains visible if regeneration fails.
- Loading and failures remain local to the overview and do not block file details.

## Validation

Regression tests cover GET never generating, explicit POST generation, cached display, disabled fallback, failure and retry/regenerate states, path changes, API encoding, mock parity, verification/cache/rate-limit behavior, plus the full backend/frontend lint, format, typecheck, test, build, and offline integration suites.

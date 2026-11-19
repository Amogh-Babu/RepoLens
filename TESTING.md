
# Testing RepoLens
 
This guide explains how to run and write tests for RepoLens. It assumes no
prior knowledge of the project, so it starts with setup and works outward.
 
RepoLens has two test suites:
 
- **Backend** (Python, pytest): unit tests, fixture-based tests on sample
  repositories, and one end-to-end test that runs the whole pipeline.
- **Frontend** (TypeScript, Vitest): unit and component tests.
---
 
## Backend (Python)
 
### Setup
 
Install [uv](https://docs.astral.sh/uv/), then from `backend/`:
 
```bash
uv sync --locked
```
 
uv installs the Python version named in `.python-version` at the repo root and
the exact dependencies in `backend/uv.lock`.
 
### Running tests
 
```bash
# Everything except end-to-end tests. This is what CI runs on every pull request.
uv run --locked python -m pytest -m "not e2e"
 
# The end-to-end test only.
uv run --locked python -m pytest -m e2e -v
 
# One file, or one test by name.
uv run --locked python -m pytest tests/test_search_scoring.py
uv run --locked python -m pytest -k parse_repo_url
```
 
### Where tests live
 
- Put tests in `backend/tests/` and name files `test_<feature>.py`.
- Name test functions `test_*` and use plain `assert` statements.
- `backend/pyproject.toml` configures pytest. It adds `backend/` to the import
  path, so tests can `import repolens` directly.
- `backend/tests/conftest.py` holds shared fixtures. For example,
  `make_search_service` builds a search service from in-memory documents, so
  search tests don't need a database.
- `backend/tests/fixtures/` holds sample repositories and their expected
  results. pytest never collects tests from this folder, so don't put test
  files there.
### Writing a backend test
 
Use `pytest.mark.parametrize` when one behavior has several inputs, and
`pytest.raises` for errors. Errors carry a `code`, `message`, and `hint`, so
assert on the ones that matter to the caller:
 
```python
import pytest
 
from repolens.ingestion import InvalidRepoUrlError, parse_repo_url
 
 
@pytest.mark.parametrize(
    "raw_url",
    [
        "https://github.com/octocat/hello-world",
        "https://github.com/octocat/hello-world.git",
    ],
)
def test_parse_repo_url_accepts_github_forms(raw_url: str) -> None:
    assert parse_repo_url(raw_url).owner == "octocat"
 
 
def test_parse_repo_url_rejects_plain_http() -> None:
    with pytest.raises(InvalidRepoUrlError) as excinfo:
        parse_repo_url("http://github.com/octocat/hello-world")
 
    assert excinfo.value.code == "INVALID_URL"
```
 
Annotate every test with `-> None` and every parameter with its type, as the
existing tests do.
 
### Faking external calls (backend)
 
The backend doesn't patch network code. Components take their transport as a
parameter: `GitHubRefResolver` takes a `url_opener`, and `GitHubSource` takes a
`fetcher`. Tests pass in a fake, so nothing touches the network. New code that
talks to an outside service should follow the same pattern.
 
### End-to-end tests
 
`backend/tests/test_e2e_reference_repo.py` runs the full pipeline on a
hand-written sample project in `backend/tests/fixtures/e2e_reference/`. It is
marked `e2e` and runs as its own job in CI.
 
Its expected results live in `expected.json`, written by hand from the sample's
source. **Don't regenerate `expected.json` from RepoLens's output.** The test
would then check the code against itself and could never fail for a wrong
result. When the output should change, edit `expected.json` by hand and explain
the change in your pull request. The sample's `README.md` lists every case it
covers.
 
### Fixture repositories and benchmarks
 
Each small sample repository under `backend/tests/fixtures/` has a README that
lists the cases it covers. Two benchmarks measure search and import
classification against hand-labeled answers:
 
```bash
python -m benchmarks.search_precision            # print the comparison table
python -m benchmarks.import_classification       # print the classification table
python -m benchmarks.import_classification --write   # update the recorded results
```
 
Only use `--write` when you intend to change the recorded numbers, and include
the new numbers in your pull request.
 
### Known failures
 
One import classification case is a known classifier bug, and the test suite
pins the current wrong answer so CI stays green. The case is
`import app.config.defaults` in the `module_directory_collision` sample. The
classifier reports an internal import, but Python raises `ModuleNotFoundError`.
 
If you fix this bug, the pinned test will fail. That's expected. In the same
pull request, update `KNOWN_MISS` and the assertion in
`tests/test_import_classification.py`, then regenerate
`benchmarks/measured_classification.json` with `--write`. Don't change the
sample's label to make the test pass.
 
### Adding a dependency
 
Dependencies are locked, and CI fails if the lockfile or exported requirements
are out of date. To add a development dependency:
 
```bash
cd backend
uv add --dev <package>
uv export --locked --no-dev --format requirements-txt --no-emit-project -o requirements.txt -q
uv export --locked --format requirements-txt --no-emit-project -o requirements-dev.txt -q
```
 
Commit `uv.lock`, `requirements.txt`, and `requirements-dev.txt` together.
 
---
 
## Frontend (TypeScript)
 
### Setup
 
From `frontend/`:
 
```bash
npm install
```
 
### Tools
 
- **Vitest** runs the tests. It's built to work with Vite, the project's build
  tool, and uses the familiar `describe`, `it`, and `expect` syntax.
- **Testing Library** (`@testing-library/react`) renders components and finds
  elements the way a user would, by label, role, or visible text.
- **user-event** (`@testing-library/user-event`) simulates typing, clicking,
  and tabbing.
- **jest-dom** adds readable assertions such as `toBeInTheDocument()`. It loads
  automatically from the shared setup file.
### Running tests
 
```bash
npm test               # run the suite once and exit
npm run test:watch     # rerun affected tests whenever you save
npm run typecheck      # TypeScript checks
npm run lint           # ESLint
```
 
### Where tests live
 
Tests sit next to the code they test. For example,
`src/components/RepoInputForm.test.tsx` is beside `RepoInputForm.tsx`. The
folders are:
 
- `src/components/`: React components
- `src/pages/`: whole pages, such as the landing page and analysis page
- `src/api/`: the API client and its mock
- `src/utils/`: plain functions with no rendering
- `src/state/`: state stores
- `src/test/`: shared test helpers, described below
### Shared test helpers
 
- **`src/test/setup.ts`** runs before every test file. It:
  - adds the jest-dom assertions;
  - clears `localStorage` and marks the first-run workspace tour as seen, so
    tests don't open the tour. A test that needs the tour clears that flag
    itself;
  - stubs browser APIs that jsdom (the test browser environment) lacks, such as
    `ResizeObserver` and `getBBox`, which the React Flow graph library needs.
- **`src/test/renderApp.tsx`** renders the entire app at a given path with a
  mock API client. Use it for page-level and routing tests:
```tsx
renderApp('/analysis/analysis-1');
```
 
  Pass a second argument to supply your own API client, for example one that
  responds slowly or returns an error.
 
### Writing a component test
 
Render the component, find elements by what a user sees, then act and assert:
 
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
 
it('enables Analyze only for a valid URL', async () => {
  const user = userEvent.setup();
  renderForm(); // a helper in this test file that renders the form with its own state
 
  const urlInput = screen.getByLabelText('GitHub repository URL');
  const analyze = screen.getByRole('button', { name: 'Analyze' });
 
  expect(analyze).toBeDisabled();
  await user.type(urlInput, 'https://github.com/pallets/flask');
  expect(analyze).toBeEnabled();
});
```
 
Guidelines:
 
- **Query like a user.** Prefer `getByRole`, `getByLabelText`, and `getByText`.
  Avoid CSS class names and test IDs unless nothing else works.
- **Use `userEvent` for interactions.** It behaves more like a real browser
  than firing events directly.
- **Name tests after behavior.** For example, `"shows the expected format after
  the user leaves the field"` says what a reader needs to know.
- **Keep a helper for setup.** When several tests need the same render, put it
  in a small function at the top of the file, as `renderForm` does.
### Faking the API (frontend)
 
Components and pages get the API client through `ApiClientContext`. Tests
provide a `MockApiClient`, with `latencyMs: 0` so responses are immediate.
Prefer providing a fake client this way over mocking `fetch` or individual
modules, because it keeps tests close to how the app actually runs.
 
---
 
## Before you open a pull request
 
- **Backend:** run `uv run --locked python -m pytest -m "not e2e"`. Also run the
  end-to-end test if you changed ingestion, analysis, storage, or search.
- **Frontend:** run `npm test`, `npm run typecheck`, and `npm run lint`.
- **Dependencies:** if you changed them, follow [Adding a dependency](#adding-a-dependency).
 

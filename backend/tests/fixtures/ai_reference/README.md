# AI summary reference repository

`repo/` is a small hand-written Python project (a note-taking service) used to
test and evaluate AI file summaries. Like the other fixtures, nothing in it is
imported or run, and pytest does not collect it.

| File | Case |
| ---- | ---- |
| `notes_app/auth.py` | No docstrings or comments: behavior only in code (passwords, signed tokens, sessions) |
| `notes_app/storage.py` | Accurate docstrings; database and file writes; class with methods |
| `notes_app/cache.py` | **Misleading docstrings** that contradict the code (claims in-memory, writes files) |
| `notes_app/sync.py` | Async functions, external dependency (`httpx`), network side effect |
| `notes_app/service.py` | Internal imports of three modules; imported by `manage.py` |
| `notes_app/plugins.py` | **Embedded prompt-injection** text in its docstring and comments |
| `notes_app/broken.py` | Invalid syntax |
| `notes_app/big_report.py` | Larger than the test input budget, so only partly inspected |
| `manage.py` | Entry point |

- `expected.json` was written by hand from the source. For each file it lists
  the behaviors an accurate summary must convey (judged against the
  implementation, not the docstrings), the symbols and internal dependencies
  it should name, the side effects it should report, and claims it must not
  make (parroted docstrings, obeyed injections).
- `answers.json` holds scripted provider answers for the offline tests:
  `good` answers written by hand, and `bad` answers that reproduce failure
  modes (invented symbols and dependencies, bad line citations, parroted
  docstrings, obeyed injections). They are not model output, so passing tests
  say nothing about a real model's accuracy.

`benchmarks/ai_summary_eval.py` scores a summary against `expected.json`. Run
it with `--live` (needs `OPENAI_API_KEY`) to evaluate the configured model on
this repository.

# Import classification fixtures

Hand-labeled repository layouts for issue #34 (Risk 2): do the imports
RepoLens resolves actually point where Python points? Each directory here is
one layout -- a `repo/` tree plus an `expected.json` naming the classification
every import in every analyzed file must get.

This is a measurement, not a feature. The labels were written from Python's
import rules before the classifier was run, and they stay that way: when the
classifier disagrees, the label keeps the correct answer and the measurement
reports a miss.

```bash
cd backend
python -m benchmarks.import_classification            # print the table
python -m benchmarks.import_classification --write    # refresh the record
python -m pytest tests/test_import_classification.py  # check and reproduce it
```

Nothing in any `repo/` tree is imported or executed; the trees are read and
`ast.parse`d like any analyzed repository, and pytest does not collect them
(`tests/conftest.py` ignores `fixtures/`).

## Measured accuracy

85 labeled references across 7 layouts. A *reference* is one
`(file, raw import name)` pair -- the unit the classifier emits. One statement
can yield several (`from library.core import Engine, engine` reaches the
package and one of its submodules) and references to one target are merged per
file, so this is not the statement count.

| layout                        | refs | correctly classified | unresolved | labeled unresolved |
| ----------------------------- | ---: | -------------------: | ---------: | -----------------: |
| src layout                    |    9 |         9 (100.0%)   |  0 (0.0%)  |                  0 |
| namespace packages            |   11 |        11 (100.0%)   |  2 (18.2%) |                  2 |
| re-exports from `__init__.py` |   11 |        11 (100.0%)   |  0 (0.0%)  |                  0 |
| relative imports              |   15 |        15 (100.0%)   |  1 (6.7%)  |                  1 |
| module/directory collision    |   11 |        10 (90.9%)    |  0 (0.0%)  |                  1 |
| monorepo source roots         |   11 |        11 (100.0%)   |  0 (0.0%)  |                  0 |
| external packages             |   17 |        17 (100.0%)   |  0 (0.0%)  |                  0 |
| **overall**                   | **85** |    **84 (98.8%)**  | **3 (3.5%)** |              **4** |

`unresolved` is the share of what the classifier emitted that it could not
resolve; `labeled unresolved` is how many references *should* be unresolved,
so the two columns separate a deliberate quiet edge from a failure. They
differ by one, and that one is the only miss.

### The one miss

```
module_directory_collision  main.py: app.config.defaults
    want unresolved, got internal app/config/defaults.py
```

`app/config.py` and `app/config/` both exist. Python resolves `app.config` to
the module, because a regular module beats a namespace-package portion, and a
module cannot hold submodules, so `import app.config.defaults` raises
`ModuleNotFoundError: No module named 'app.config.defaults'; 'app.config' is
not a package`. The file `app/config/defaults.py` is unreachable by any import
statement. The classifier resolves the dotted name by path arithmetic and
reports an internal edge to it.

The label stays `unresolved`.
`tests/test_import_classification.py::test_the_only_miss_is_the_known_classifier_error`
asserts the classifier still gets it wrong, so fixing `classifier.py` fails
that test and the fixture needs no change.

## Labeling rules

Every label follows these, in order, and each was checked against CPython by
putting the layout on `sys.path` and asking `importlib` where the name
resolves:

1. A reference resolves to the file Python would run for it. A regular package
   (`pkg/__init__.py`) beats a same-named module (`pkg.py`), which beats a
   directory with no `__init__.py`.
2. `from pkg import name` where `name` is a submodule resolves to the
   submodule file -- the file that defines the code, not the package that
   forwards it.
3. `from pkg import name` where `name` is not a submodule resolves to
   `pkg/__init__.py`, which is the file that defines the re-exported name.
4. A dotted absolute import is `external` when its top-level name is not in
   the importing file's import roots, and the reported package is only that
   top-level name (`os.path` is `os`).
5. A reference that points inside the repository but names no module file is
   `unresolved`. A namespace package is in this group: it is importable, but
   no file runs for it, so there is nothing to point at.
6. An absolute import of a missing submodule is labeled with its closest
   parent package, which is the nearest file that does run. This follows the
   rule `backend/README.md` documents, and it is the one rule here that is
   RepoLens' convention rather than a plain readback of CPython.

## What each layout covers

| Layout                         | Cases                                                                                                                                                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src_layout`                   | A package under `src/`, imported absolutely from inside `src/` and from a sibling `tests/` tree, which is the installed-distribution case: `tests/test_catalog.py` must reach `src/shopfront/`.    |
| `namespace_packages`           | PEP 420 packages with no `__init__.py` anywhere, so every directory looks like a source root. Submodules resolve; the namespace packages themselves (`telemetry.metrics`, `telemetry.transport`) are unresolved because no file runs for them. Includes a relative import inside a namespace package. |
| `reexports`                    | `library/core/__init__.py` re-exports names its submodules define. Covers a re-export only (`consumer.py`), a submodule only, a statement mixing both (`library/plugins/__init__.py`), and a star import. |
| `relative_imports`             | Depth 1 (`from . import pricing`), depth 2 (`from .. import config`, `from ..config import ...`), depth 3 (`from ...config import ...`), `from .subpkg import <submodule>`, and one relative import of a file that does not exist (unresolved). |
| `module_directory_collision`   | `app/config.py` beside `app/config/` (module beats the namespace portion) and `app/models.py` beside `app/models/__init__.py` (package beats module). Also guards the regression where an imported name was tried as a submodule before the base module resolved: `from app.config import defaults` must reach `app/config.py`, not `app/config/defaults.py`. |
| `monorepo_source_roots`        | Two sibling checkouts that each hold their own `app` package. Guards the regression where an absolute import fell through to a source root outside the importing tree: `app.config` in `service_b/` must resolve inside `service_b/`, and `app.legacy`, which only `service_a/` has, must not cross over. |
| `external_packages`            | Standard library (`os.path`, `sys`, `xml.etree.ElementTree`, `collections.abc`, `__future__`) and third-party (`requests`, `flask`, `sqlalchemy.orm`, `httpx`) imports that must stay external, each reported by its top-level package. Plus the two shadowing cases: a root-level `queue.py` that *does* shadow the stdlib (internal), and `pkg/json.py`, which does not, because absolute `import json` inside a package is still the stdlib (external). |

## `expected.json`

- `title`, `summary`: the layout's name in the report and one line on what it covers.
- `imports`: analyzed file path -> a list of `[rawName, kind, target]`. The
  target is the repository path for an `internal` import, the top-level
  package for an `external` one, and `null` when `unresolved`. Every analyzed
  file needs an entry, `[]` included, so no file can drop out of the score
  unnoticed.

## Changing it

If you change a `repo/` tree, re-label `expected.json` by hand from the rules
above and re-run `python -m benchmarks.import_classification --write`, then
explain the change in the pull request. Do not label a reference from the
classifier's own output, and do not relabel a reference to turn a miss into a
pass: the measurement is only worth running while the labels are independent
of the code under test.

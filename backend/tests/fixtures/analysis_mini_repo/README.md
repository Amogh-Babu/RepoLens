# Analysis mini repository

A small Python tree for checking that `repolens.analysis` reports imports and
top-level symbols per file. The tests only read and `ast.parse` these files;
they are never imported or executed.

The tree deliberately covers:

- absolute, stdlib, dotted, and aliased imports (`app/main.py`)
- relative imports at one and two levels, including `from .. import config`
  (`app/services/__init__.py`, `app/services/billing.py`)
- a star import (`app/__init__.py`)
- an import inside a function body (`app/main.py`)
- top-level functions, async functions, classes, and variables, with methods
  and nested definitions left out of the top-level symbol list
- a file that does not parse (`app/services/broken.py`)
- a file no analyzer supports (`notes.md`)

Keep the tree small enough to review by hand, and update
`tests/test_analysis_mini_repo.py` whenever the fixture source changes.

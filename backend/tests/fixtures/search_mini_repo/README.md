# Search mini repository

This fixture is a small, hand-annotated Python repository for checking feature
search and reading order. Its source files are never imported or executed by
the tests. `search_index.json` represents the normalized records that a
completed analyzer and graph store should provide to `SearchIndex`.

The expected query paths are recorded in `search_cases.json`. Keep the fixture
small enough to review manually. Update the index and query cases whenever the
fixture source changes.

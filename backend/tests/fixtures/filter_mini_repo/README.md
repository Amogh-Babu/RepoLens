# Filter mini repository

A small tree for checking that `repolens.ingestion.SourceFileFilter` keeps
vendored, generated, and oversized files away from the analyzers. The tests
read, size, and `ast.parse` these files; they are never imported or executed.

The tree deliberately covers:

- the repository's own source, which must be analyzed (`app/__init__.py`,
  `app/helpers.py`, `app/main.py`)
- vendored third-party code in `vendor/` and `third_party/`, written in
  Python so an exclusion cannot be mistaken for "no analyzer supports it"
- a vendored directory of another language (`node_modules/left-pad/index.js`)
- generated Python by file name (`app/schema_pb2.py`,
  `app/settings_generated.py`) and by directory (`build/bundled_app.py`,
  `app.egg-info/entry_points.py`)
- a minified asset (`static/app.min.js`) and a lock file
  (`package-lock.json`)
- a hand-written file that is large for this tree (`app/bulk_table.py`, about
  1.5 KB), so a test can lower `ArchiveLimits.max_file_bytes` to 1024 and see
  only that file excluded as oversized
- a file no analyzer supports and no rule excludes (`docs/notes.md`), which
  belongs in `skipped_paths` rather than in the exclusions

Keep the tree small enough to review by hand, and update
`tests/test_ingestion_filter.py` and `tests/test_analysis_filtering.py`
whenever it changes.

# Ingestion

The ingestion component turns a public GitHub repository at a specific commit
into a filtered, safe snapshot for analysis. It never runs, imports or builds
any code from the repository.

## Input

- `url`: a public GitHub repository URL.
- `ref` (optional): a branch, tag or commit SHA. Defaults to the repository's
  default branch.

The ref is always resolved to a full 40-character commit SHA before download.
Everything downstream (cache, graph, source links) uses the SHA, never the ref.

## URL rules

Accepted forms:

- `https://github.com/<owner>/<repo>`
- the same with a trailing `/` or `.git`
- `https://github.com/<owner>/<repo>/tree/<ref>` where `<ref>` has no slash

Rejected with `INVALID_URL` or `UNSUPPORTED_HOST`:

- any scheme other than `https`
- any host other than `github.com` (`www.github.com` is normalized)
- embedded credentials (`user:pass@`), ports, query strings and fragments
- extra path segments (`/blob/...`, `/issues`, `/tree/` with a slash in the ref)
- names that break GitHub's rules: owner 1-39 characters (letters, digits,
  hyphens); repo 1-100 characters (letters, digits, `-`, `_`, `.`), not `.` or `..`

Refs containing slashes (e.g. `feature/x`) go in the `ref` field, not the URL.
A `ref` allows letters, digits, `.`, `_`, `-` and `/`, up to 200 characters,
with no `..` and no leading `-`. Validation runs before any network call.

## Limits

| Limit | Value | Source |
| --- | --- | --- |
| Python files after filtering | 1,000 | Pitch doc |
| Total ingest + analysis time | 3 minutes | Pitch doc |
| Cache lifetime | 24 hours | Pitch doc |
| Connect timeout | 10 s | Proposed |
| Total download timeout | 60 s | Proposed |
| Max archive size | 100 MB | Proposed |
| Max extracted size | 200 MB | Proposed |
| Max archive entries | 20,000 | Proposed |
| Max single `.py` file | 1 MB | Proposed |

The file cap counts `.py` files that remain after filtering. Size limits are
checked while streaming, not only from headers.

## Filtering

Only `.py` files are kept. These are excluded and counted in `excluded_count`:

- vendored or environment directories: `.git`, `node_modules`, `venv`, `.venv`,
  `site-packages`, `__pycache__`
- build output: `build/`, `dist/`
- generated files: names like `*_pb2.py`, or a "generated" / "do not edit"
  marker in the first few lines

## Safety rules

- Repository code is never executed, imported or built.
- Only regular files are extracted. Symlinks, hard links and special files are
  skipped.
- Entries with absolute paths or `..` are rejected, so nothing escapes the
  snapshot directory.
- The snapshot directory is deleted after analysis, on success and on error.
- No credentials or user data are stored.

## Cache key

`(owner/repo lowercased, full SHA)`. GitHub names are case-insensitive, so
lowercasing avoids duplicate entries.

## Errors

Every failure is a `RepolensError` with `{code, message, hint}`.

| Code | When | Hint |
| --- | --- | --- |
| `INVALID_URL` | malformed URL or ref | Use `https://github.com/<owner>/<repo>`. |
| `UNSUPPORTED_HOST` | not GitHub | Only github.com is supported. |
| `REPO_NOT_FOUND` | missing or private (GitHub returns 404 for both) | Check the spelling and that the repo is public. |
| `NO_PYTHON_FILES` | zero `.py` files after filtering | RepoLens supports Python repos only. |
| `REPO_TOO_LARGE` | over the file, archive or extracted-size limit | Try a smaller repo (max 1,000 Python files). |
| `RATE_LIMITED` | GitHub rate limit hit | Wait a few minutes and retry. |
| `DOWNLOAD_FAILED` | timeout, network error or 5xx | Retry shortly. |

## Open questions

- Should `/tree/<ref>` URLs be parsed or rejected?
- Does the analysis component want file contents or paths on disk?
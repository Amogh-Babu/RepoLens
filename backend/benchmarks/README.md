# Search precision measurement

Does RepoLens search beat grep? This is the measurement behind issue #37
(Risk 1). It is not a feature: nothing here changes ranking, and the numbers
are reported as measured.

```bash
cd backend
python -m benchmarks.search_precision            # print the comparison table
python -m benchmarks.search_precision --write    # refresh measured_precision.json
python -m pytest tests/test_search_precision.py  # check and reproduce it
```

## Measured top-5 precision

| repository           | queries | indexed files | RepoLens | grep  | grep+rank | ideal |
| -------------------- | ------: | ------------: | -------: | ----: | --------: | ----: |
| `search_mini_repo`   |       6 |             8 |    0.167 | 0.033 |     0.033 | 0.267 |
| `analysis_mini_repo` |       6 |             7 |    0.167 | 0.000 |     0.000 | 0.233 |
| `e2e_reference`      |       7 |            14 |    0.286 | 0.086 |     0.114 | 0.457 |
| **overall**          |  **19** |               |**0.211** |**0.042**| **0.053**|**0.326**|

RepoLens beats the grep filename baseline on all three repositories: 0.211
versus 0.042 overall, five times the baseline, and it never scores below it on
a single query. Read as a share of what a perfect ranker could score on these
labels, RepoLens recovers 65% of the achievable precision and grep recovers
13%.

Per-query results, including every path each system returned, are in
`measured_precision.json`.

### Reading the numbers

`precision@5` is the standard definition: labeled files in the top five,
divided by five. These fixture repositories hold 7 to 14 files and most
queries have one or two labeled files, so no system can reach 1.000. The
`ideal` column is the score a perfect ranker would get on the same labels, and
every system shares that ceiling. Compare systems to each other and to
`ideal`; the absolute values do not transfer to a large repository.

### Where RepoLens loses or ties

grep never wins a query outright, and RepoLens scores at least as well as both
baselines on all 19. The ties are the three queries whose answer is named in a
filename -- `payments`, `user account lookup`, and `login` on `e2e_reference`
-- which is exactly the case grep handles.

Across the 19 queries, RepoLens finds 20 of the 31 labeled files a perfect
ranker would have returned. Every one of the 11 it misses is a recall failure,
not a ranking failure: the file is never a candidate, because no query term
appears in its path, its module-level symbol names, or its import names, which
is all the index holds.

- Four queries return **nothing at all**: `http request handler`, `tax`,
  `command line arguments`, and `command line entry point`. Together they
  account for 5 of the 11 misses.
- The other 6 are files whose matching text sits somewhere the index does not
  reach -- a dataclass field (`Settings.tax_rate`, `User.cart`), a method
  (`User.check_password`), a dict key (`password_hash`), or an imported name
  (`from bookshop.config import SECRET_KEY`, where only the module
  `bookshop.config` is stored).

## Method

Every system answers the same hand-labeled queries, measured at k = 5.

**RepoLens** is measured through its production path, not through a fixture
index: `AnalysisService` parses the tree, `classify_imports` resolves its
imports, the result is stored in an in-memory `SqliteGraphStore`, and that
store serves `SearchService` as the `SearchIndex`. This is the sequence
`PipelineAnalysisRunner` runs for a real repository, so the measurement sees
the same documents the API serves. It notably means comments are not indexed:
`SearchService` scores a `comment` field, but
`repolens.analysis.adapter.to_analyzed_file` never produces a `CommentRecord`,
so in production that field is always empty. Measuring against
`tests/fixtures/search_mini_repo/search_index.json`, whose comments are
hand-written, would have overstated RepoLens.

**grep** is the baseline the issue names, a grep of the file list:

```bash
git ls-files | grep -i -E 'term1|term2'
```

A path matches when any query term is a case-insensitive substring of it,
directories included, and the matches stay in the sorted listing order grep
was given. grep sees *every* file in the tree (11, 9, and 16 files, against
the 8, 7, and 14 RepoLens indexes), including the Markdown and
`requirements.txt` files RepoLens cannot analyze.

**grep+rank** is the same matches with the cheapest possible ranking added:
sort by how many query terms the path contains, then by path. Plain grep
cannot order its output, which costs it whenever a term appears in more than
five paths. Exactly one query does that -- `book search by title` matches 12
of the 16 files in the bookshop tree, because every one of them is under
`bookshop/` -- so grep+rank differs from grep on that query alone. It exists
so the headline result does not rest on grep having no ranking at all, and it
still loses by 4x.

Both baselines tokenize the query exactly as `SearchService` does -- distinct,
case-folded `\w+` runs -- which `tests/test_search_precision.py` asserts
directly against `SearchService._parse_query`.

## The labels

`labeled_queries.json` holds 19 queries over three repositories, with the
labeling rule and a per-query rationale. The rule:

> A file is relevant to a query if a developer asked to understand or change
> that feature would have to open it: it either implements the named behavior
> or defines a step the behavior delegates to by name. A package
> `__init__.py` that only holds a docstring or re-exports a name is not
> relevant, because it contains nothing to read about the feature. A test of
> the named behavior is relevant.

The labels were written from the fixture source before either system was run,
and were not revised afterwards. The queries are feature-shaped, the way a
reader describes what they are looking for, rather than identifiers copied out
of the code; four of them happen to match no indexed text at all, and those
were kept.

The three repositories are the existing fixtures
(`tests/fixtures/search_mini_repo`, `tests/fixtures/analysis_mini_repo`, and
`tests/fixtures/e2e_reference/repo`). They were written for other tests before
this measurement existed, so the corpus was not shaped to favor either system.
No repository is fetched; nothing in them is imported or executed.

## Changing it

`measured_precision.json` is a record of an observation, not a hand-written
expectation: regenerate it with `--write` when ranking or indexing changes on
purpose, and say in the pull request which numbers moved and why. Adding
queries or repositories means editing `labeled_queries.json`; label the files
before looking at what any system returns, and keep the rationale.

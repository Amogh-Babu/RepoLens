# Search precision measurement

How much does local semantic search improve RepoLens over keyword-only search
and grep? This is the measurement for issue #77; the recorded numbers are
generated from the production pipeline and the pinned BGE-small model.

```bash
cd backend
python -m benchmarks.search_precision            # print the comparison table
python -m benchmarks.search_precision --write    # refresh measured_precision.json
python -m pytest tests/test_search_precision.py  # check labels and recorded gates
```

## Measured top-5 precision

| repository           | queries | indexed files | keyword | hybrid | grep  | grep+rank | ideal |
| -------------------- | ------: | ------------: | ------: | -----: | ----: | --------: | ----: |
| `search_mini_repo`   |       6 |             8 |   0.200 |  0.267 | 0.033 |     0.033 | 0.267 |
| `analysis_mini_repo` |       6 |             7 |   0.233 |  0.233 | 0.000 |     0.000 | 0.233 |
| `e2e_reference`      |       8 |            14 |   0.300 |  0.400 | 0.075 |     0.125 | 0.475 |
| **overall**           | **20** |               | **0.250** | **0.310** | **0.040** | **0.060** | **0.340** |

Hybrid is no worse than keyword-only on every query and improves overall
precision@5 from 0.250 to 0.310. It finds a labeled file for the vague
production-onboarding query and for `tax`, both of which keyword-only search
could not answer. The model is `BAAI/bge-small-en-v1.5`; its vectors and query
inference are local.

### History

| change | keyword precision@5 | hybrid precision@5 |
| ------ | ------------------: | -----------------: |
| Keyword index, class members, docstrings and comments | 0.250 | 0.310 |

The recorded hybrid results preserve the keyword-only top-five on every query.
Semantic-only results are appended after those exact hits so their graph edges
cannot push a strong keyword match below the fold.

Per-query results, including every path each system returned, are in
`measured_precision.json`. Its precision and non-regression checks run in CI
without downloading the model; the benchmark command itself uses FastEmbed.

### Reading the numbers

`precision@5` is the standard definition: labeled files in the top five,
divided by five. These fixture repositories hold 7 to 14 files and most
queries have one or two labeled files, so no system can reach 1.000. The
`ideal` column is the score a perfect ranker would get on the same labels, and
every system shares that ceiling. Compare systems to each other and to
`ideal`; the absolute values do not transfer to a large repository.

### Where Hybrid Helps

Hybrid search recovers files that do not repeat the query wording: `tax` finds
`app/billing/service.py`, `password verification` finds the user repository,
and `login` finds the token and user-model dependencies. The vague production
onboarding query returns `bookshop/config.py`; conventional entry-point
identification and the repo-wide guided tour are handled separately by #79.

The benchmark remains small and Python-only. Its 0.310 precision@5 is a
comparison on these fixture labels, not a prediction for every large
repository. Semantic-only suggestions are added after exact-match results, so
they can improve recall without displacing existing keyword hits.

## Method

Every system answers the same hand-labeled queries, measured at k = 5.

**RepoLens keyword** and **RepoLens-hybrid** use the same production pipeline:
`AnalysisService` parses the tree, `classify_imports` resolves imports, and an
in-memory `SqliteGraphStore` indexes the parsed records. Keyword-only disables
vector candidates. Hybrid stores bounded per-file text chunks with BGE-small
vectors and combines semantic and keyword ranks. This follows the parse,
classify, index and store sequence in `PipelineAnalysisRunner`; no fixture file
is imported or executed.

`python -m benchmarks.search_precision` uses FastEmbed and the pinned model.
Tests inject `HashEmbedder`, so CI checks labels and keyword reproducibility
without downloading model weights; a separate test checks the recorded BGE run
meets the per-query non-regression gate.

**grep** is the baseline the issue names, a grep of the file list:

```bash
git ls-files | grep -i -E 'term1|term2'
```

A path matches when any query term is a case-insensitive substring of it,
directories included, and the matches stay in the sorted listing order grep
was given. The listing really is `git ls-files`: taking the repository's
tracked files rather than walking the directory keeps ignored and untracked
working-tree files -- a `.DS_Store`, a cache, a local scratch file -- from
changing what the baseline matches, so the recorded numbers do not depend on
whose checkout the measurement ran in. grep sees *every* file the repository
tracks (11, 9, and 16 files, against the 8, 7, and 14 RepoLens indexes),
including the Markdown and `requirements.txt` files RepoLens cannot analyze.

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

`labeled_queries.json` holds 20 queries over three repositories, with the
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
of the code. The production-onboarding query is intentionally vague and has no
keyword match in the analyzed source.

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

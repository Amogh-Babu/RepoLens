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
| `search_mini_repo`   |       6 |             8 |   0.167 |  0.200 | 0.033 |     0.033 | 0.267 |
| `analysis_mini_repo` |       6 |             7 |   0.200 |  0.233 | 0.000 |     0.000 | 0.233 |
| `e2e_reference`      |       8 |            14 |   0.250 |  0.325 | 0.075 |     0.125 | 0.475 |
| **overall**           | **20** |               | **0.210** | **0.260** | **0.040** | **0.060** | **0.340** |

The model is `BAAI/bge-small-en-v1.5` with its retrieval query instruction;
its vectors and query inference are local. Hybrid meets keyword-only hits on
every query in this recorded run.

### History

| change | keyword precision@5 | hybrid precision@5 |
| ------ | ------------------: | -----------------: |
| Before weak-match filtering, current index and BGE query instruction | 0.210 | 0.280 |
| Weak-match filtering and relevance-aware reading order | 0.210 | 0.260 |

The cutoff removes irrelevant results but also loses relevant low-similarity
matches: `tax`, `http request handler`, `secret key`'s token dependency, and
the vague onboarding query. It returns 26 labeled hits among 55 results,
against 28 among 100 before the change: returned-result precision improves
from 0.280 to 0.473, while fixed-denominator precision@5 drops from 0.280 to
0.260. The two metrics answer different questions; neither demonstrates
general-purpose accuracy.

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

### Where Hybrid Helps and Misses

Hybrid search recovers files that do not repeat the query wording: `password
verification` finds the user repository and `command line arguments` finds
`app/main.py`. Other valid searches, including `tax`, now return no result.
Semantic cosine scores are not calibrated probabilities; no single threshold
reliably separates relevance from irrelevance across all queries.

The benchmark remains small and Python-only. Its 0.260 precision@5 is a
comparison on these fixture labels, not a prediction for every large
repository. Reading order can still change which results appear in the top five.

## Independent repository checks

`external_search.py` uses the production index and model on three local
checkouts without executing their code. Guide-backed paths are starting points,
not exhaustive relevance labels, so these checks are not a precision estimate.
Use pinned revisions and run from `backend/`:

```bash
git clone https://github.com/lgeeklee/pyvmomi-tools.git /tmp/repolens-pyvmomi
git -C /tmp/repolens-pyvmomi checkout 1f9129a42a2c477d18b15f438aeedb1a2ec4c1fe
git clone https://github.com/pallets/flask.git /tmp/repolens-flask
git -C /tmp/repolens-flask checkout 49943b5a94413a530761350f04e896f76e8d620e
git clone https://github.com/borh-lab/natsume-simple.git /tmp/repolens-natsume
git -C /tmp/repolens-natsume checkout ddc74c92d10bdb7750cbf20e1dd66e2a17b0d357
python -m benchmarks.external_search --issue /tmp/repolens-pyvmomi --flask /tmp/repolens-flask --natsume /tmp/repolens-natsume
```

The [Flask request walkthrough](https://github.com/sangameshh31/flask-request-lifecycle-investigation/blob/d826e14a90217d8cca1a3d98fb3e26c2166d7cae/README.md)
identifies request dispatch in `src/flask/app.py` and its test; the
[natsume walkthrough](https://github.com/borh-lab/natsume-simple/blob/ddc74c92d10bdb7750cbf20e1dd66e2a17b0d357/README.md)
identifies its pipeline, extraction, registry and API files. In the recorded
run, nine of eleven negative queries returned no results; `marine biology`
still returned results in Flask and natsume. Nine of eleven positive queries
returned at least one named starting point in the top five. The Flask callback
and server queries each missed one of their two named files, and the natsume
stored-corpus validation query missed its named registry file. The issue
repository's snapshot query missed `py-snaplist.py`: its Python 2 exception
syntax fails the Python 3 parser, leaving it without searchable symbols.
Search cannot recover content that was not parsed.

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

# Memory and time of a real analysis

`memory_profile.py` measures what issue #118 reported: peak memory and stage
times of one analysis of a real GitHub repository, followed by a few searches.
It runs the production pipeline and model inline and prints JSON.

```bash
cd backend
python -m benchmarks.memory_profile https://github.com/numpy/numpy
python -m benchmarks.memory_profile https://github.com/numpy/numpy --abort-above-mib 3000
```

`peakRssMiB` is the process's peak resident memory, which is what an
out-of-memory killer acts on; `stagePeakRssMiB` attributes it to pipeline
stages. `--abort-above-mib` stops the run before a machine starts swapping.
The recorded numbers are in the top-level README under *System requirements*.

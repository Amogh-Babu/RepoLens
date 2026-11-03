"""Measure top-5 search precision against a grep filename baseline.

This answers one question: does RepoLens search put the files a reader needs
in the first five results more often than grepping the file list does? Every
system is measured on the same hand-labeled queries in `labeled_queries.json`,
whose labels were written from the fixture source before any system was run.

RepoLens is measured through its production path: the fixture tree is parsed
by `AnalysisService`, its imports are classified by `classify_imports`, the
result is stored in an in-memory `SqliteGraphStore`, and that store serves
`SearchService` as the `SearchIndex` -- the same sequence
`PipelineAnalysisRunner` performs for a real repository. No fixture file is
imported or executed.

Run it from `backend/`:

    python -m benchmarks.search_precision            # print the table
    python -m benchmarks.search_precision --write    # refresh the record
"""

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files
from repolens.graph import AnalysisRecord, SqliteGraphStore
from repolens.search import SearchService


BENCHMARK_ROOT = Path(__file__).parent
BACKEND_ROOT = BENCHMARK_ROOT.parent
QUERIES_PATH = BENCHMARK_ROOT / "labeled_queries.json"
RECORD_PATH = BENCHMARK_ROOT / "measured_precision.json"

REPOLENS = "repolens"
GREP = "grep"
GREP_RANKED = "grep_ranked"

# The systems compared, in the order the table reports them.
SYSTEMS: tuple[str, ...] = (REPOLENS, GREP, GREP_RANKED)
SYSTEM_LABELS = {
    REPOLENS: "RepoLens",
    GREP: "grep",
    GREP_RANKED: "grep+rank",
}

# Mirrors `SearchService._parse_query`, so every baseline searches for exactly
# the terms RepoLens searches for; `tests/test_search_precision.py` asserts the
# two stay in agreement.
_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)

# Directories a `git ls-files` listing would never contain.
_UNLISTED_DIRECTORY_NAMES = frozenset({".git", ".hg", ".svn", "__pycache__"})

_ANALYSIS_ID = "precision-benchmark"
_BENCHMARK_REPO_URL = "https://github.com/repolens/benchmark"
_SHA = "0" * 40


@dataclass(frozen=True)
class LabeledQuery:
    """One query and the files a reader asking it needs to open."""

    query: str
    relevant: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class RepoQuerySet:
    """A fixture repository and its labeled queries."""

    id: str
    name: str
    root: Path
    queries: tuple[LabeledQuery, ...]


@dataclass(frozen=True)
class QueryResult:
    """What every system returned for one query, against its labels."""

    query: str
    relevant: tuple[str, ...]
    rankings: dict[str, tuple[str, ...]]
    top_k: int

    def hits(self, system: str) -> int:
        """Count the labeled files `system` placed in its top k."""
        return len(set(self.rankings[system]).intersection(self.relevant))

    def precision(self, system: str) -> float:
        """Return `system`'s precision@k: relevant results over k."""
        return self.hits(system) / self.top_k

    @property
    def ideal_hits(self) -> int:
        """The most labeled files any ranker could fit in the top k."""
        return min(self.top_k, len(self.relevant))

    @property
    def ideal_precision(self) -> float:
        """The precision@k a perfect ranker would score on this query."""
        return self.ideal_hits / self.top_k


@dataclass(frozen=True)
class RepoResult:
    """Every query result for one repository, with what each system could see."""

    repo: RepoQuerySet
    indexed_paths: tuple[str, ...]
    listed_paths: tuple[str, ...]
    results: tuple[QueryResult, ...]

    def precision(self, system: str) -> float:
        """Return `system`'s mean precision@k over this repository's queries."""
        return _mean(result.precision(system) for result in self.results)

    @property
    def ideal_precision(self) -> float:
        return _mean(result.ideal_precision for result in self.results)


@dataclass(frozen=True)
class Measurement:
    """The whole measurement: every repository, every query.

    The overall numbers are the mean over all queries, so a repository with
    more labeled queries weighs more; the per-repository means are reported
    alongside them.
    """

    top_k: int
    repos: tuple[RepoResult, ...]

    @property
    def results(self) -> tuple[QueryResult, ...]:
        return tuple(result for repo in self.repos for result in repo.results)

    def precision(self, system: str) -> float:
        """Return `system`'s mean precision@k over every labeled query."""
        return _mean(result.precision(system) for result in self.results)

    @property
    def ideal_precision(self) -> float:
        return _mean(result.ideal_precision for result in self.results)


def query_terms(query: str) -> tuple[str, ...]:
    """Split a query into the distinct, case-folded terms every system matches."""
    return tuple(
        dict.fromkeys(term.casefold() for term in _TOKEN_PATTERN.findall(query))
    )


def load_query_sets(
    queries_path: Path = QUERIES_PATH,
) -> tuple[int, tuple[RepoQuerySet, ...]]:
    """Read the labeled queries, returning the top-k setting and the repositories."""
    data = json.loads(queries_path.read_text(encoding="utf-8"))
    repos = tuple(
        RepoQuerySet(
            id=repo["id"],
            name=repo["name"],
            root=BACKEND_ROOT / repo["root"],
            queries=tuple(
                LabeledQuery(
                    query=case["query"],
                    relevant=tuple(case["relevant"]),
                    rationale=case["rationale"],
                )
                for case in repo["queries"]
            ),
        )
        for repo in data["repos"]
    )
    return int(data["top_k"]), repos


def build_search_service(root: Path) -> tuple[SearchService, tuple[str, ...]]:
    """Index a repository tree the way the analysis pipeline does.

    The tree is parsed and its imports classified, then stored in an in-memory
    graph store that serves as the search index. Files are read as text only;
    none is imported or executed.

    Returns:
      The search service, and the repository-relative paths it indexed.
    """
    analysis = AnalysisService().analyze_repository(root)
    store = SqliteGraphStore()
    store.save(
        AnalysisRecord(
            analysis_id=_ANALYSIS_ID,
            repo=_BENCHMARK_REPO_URL,
            sha=_SHA,
            status="completed",
            files=classify_imports(to_analyzed_files(analysis)),
        )
    )
    indexed = tuple(
        document.path for document in store.get_search_documents(_ANALYSIS_ID)
    )
    return SearchService(store), indexed


def repolens_top_paths(
    service: SearchService, query: str, top_k: int
) -> tuple[str, ...]:
    """Return the paths RepoLens puts first for a query."""
    page = service.search(_ANALYSIS_ID, query, limit=top_k)
    return tuple(result.path for result in page.results)


def list_repository_paths(root: Path) -> tuple[str, ...]:
    """List every file in the tree, sorted, the way `git ls-files` would."""
    paths = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and _UNLISTED_DIRECTORY_NAMES.isdisjoint(path.relative_to(root).parts)
    ]
    return tuple(sorted(paths))


def grep_matches(paths: Iterable[str], query: str) -> tuple[str, ...]:
    """Return every listed path containing a query term, in listing order.

    A path matches when any query term is a case-insensitive substring of it,
    directories included, which is what

        git ls-files | grep -i -E 'term1|term2'

    prints. The listing is sorted, and grep preserves its input order.
    """
    terms = query_terms(query)
    return tuple(
        path for path in paths if any(term in path.casefold() for term in terms)
    )


def baseline_top_paths(
    paths: tuple[str, ...], query: str, top_k: int
) -> tuple[str, ...]:
    """Return the first `top_k` paths a grep of the file list would print.

    This is the baseline the issue names. grep has no notion of relevance, so
    which five of its matches a reader sees first is decided by path order.
    """
    return grep_matches(paths, query)[:top_k]


def ranked_baseline_top_paths(
    paths: tuple[str, ...], query: str, top_k: int
) -> tuple[str, ...]:
    """Return grep's matches ordered by how many query terms each path contains.

    Plain grep cannot order its output, which costs it whenever a query term
    appears in more than `top_k` paths. This variant gives the baseline the
    cheapest possible ranking -- sort the same matches by matched term count,
    then by path -- so the comparison does not rest on grep's lack of ordering.
    """
    terms = query_terms(query)
    matched = grep_matches(paths, query)
    ordered = sorted(
        matched,
        key=lambda path: (
            -sum(term in path.casefold() for term in terms),
            path.casefold(),
        ),
    )
    return tuple(ordered[:top_k])


def measure(queries_path: Path = QUERIES_PATH) -> Measurement:
    """Run every labeled query through RepoLens search and the baselines."""
    top_k, repos = load_query_sets(queries_path)
    repo_results: list[RepoResult] = []
    for repo in repos:
        service, indexed = build_search_service(repo.root)
        listed = list_repository_paths(repo.root)
        results = tuple(
            QueryResult(
                query=case.query,
                relevant=case.relevant,
                rankings={
                    REPOLENS: repolens_top_paths(service, case.query, top_k),
                    GREP: baseline_top_paths(listed, case.query, top_k),
                    GREP_RANKED: ranked_baseline_top_paths(listed, case.query, top_k),
                },
                top_k=top_k,
            )
            for case in repo.queries
        )
        repo_results.append(
            RepoResult(
                repo=repo, indexed_paths=indexed, listed_paths=listed, results=results
            )
        )
    return Measurement(top_k=top_k, repos=tuple(repo_results))


def to_record(measurement: Measurement) -> dict:
    """Describe a measurement as the JSON the recorded results file holds."""
    return {
        "top_k": measurement.top_k,
        "overall": {
            "queries": len(measurement.results),
            "precision": {
                system: round(measurement.precision(system), 4) for system in SYSTEMS
            },
            "ideal_precision": round(measurement.ideal_precision, 4),
        },
        "repos": [
            {
                "id": repo.repo.id,
                "indexed_files": len(repo.indexed_paths),
                "listed_files": len(repo.listed_paths),
                "precision": {
                    system: round(repo.precision(system), 4) for system in SYSTEMS
                },
                "ideal_precision": round(repo.ideal_precision, 4),
                "queries": [
                    {
                        "query": result.query,
                        "relevant": list(result.relevant),
                        "ideal_hits": result.ideal_hits,
                        "hits": {
                            system: result.hits(system) for system in SYSTEMS
                        },
                        "top": {
                            system: list(result.rankings[system])
                            for system in SYSTEMS
                        },
                    }
                    for result in repo.results
                ],
            }
            for repo in measurement.repos
        ],
    }


def load_record(record_path: Path = RECORD_PATH) -> dict:
    """Read the recorded measurement the test compares a fresh run against."""
    return json.loads(record_path.read_text(encoding="utf-8"))


def write_record(measurement: Measurement, record_path: Path = RECORD_PATH) -> None:
    """Overwrite the recorded measurement with a fresh one."""
    record_path.write_text(
        json.dumps(to_record(measurement), indent=2) + "\n", encoding="utf-8"
    )


def format_report(measurement: Measurement) -> str:
    """Render the comparison as the table this script prints."""
    k = measurement.top_k
    header = f"{'repository':<22}{'queries':>8}{'files':>7}"
    header += "".join(f"{SYSTEM_LABELS[system]:>11}" for system in SYSTEMS)
    header += f"{'ideal':>8}"
    rule = "-" * len(header)

    lines = [
        f"Top-{k} search precision: RepoLens vs. a grep filename baseline",
        "",
        header,
        rule,
    ]
    for repo in measurement.repos:
        row = f"{repo.repo.id:<22}{len(repo.results):>8}{len(repo.indexed_paths):>7}"
        row += "".join(f"{repo.precision(system):>11.3f}" for system in SYSTEMS)
        row += f"{repo.ideal_precision:>8.3f}"
        lines.append(row)
    lines.append(rule)
    overall = f"{'overall':<22}{len(measurement.results):>8}{'':>7}"
    overall += "".join(f"{measurement.precision(system):>11.3f}" for system in SYSTEMS)
    overall += f"{measurement.ideal_precision:>8.3f}"
    lines.extend(
        [
            overall,
            "",
            "'grep' is the baseline the issue names: a path-order grep of the file",
            "list. 'grep+rank' is the same matches ordered by matched term count.",
            "'ideal' is what a perfect ranker would score: most queries have fewer",
            f"than {k} labeled files, so precision@{k} cannot reach 1.000 here. Every",
            "system shares that ceiling.",
            "",
        ]
    )

    for repo in measurement.repos:
        lines.append(f"{repo.repo.id} ({repo.repo.name})")
        for result in repo.results:
            scores = ", ".join(
                f"{SYSTEM_LABELS[system]} {result.hits(system)}/{result.ideal_hits}"
                for system in SYSTEMS
            )
            lines.append(f"  {result.query!r}: {scores}")
            lines.append(f"    {'labeled':<9}: {', '.join(result.relevant)}")
            for system in SYSTEMS:
                ranking = _render_ranking(result.rankings[system], result.relevant)
                lines.append(f"    {SYSTEM_LABELS[system]:<9}: {ranking}")
        lines.append("")
    return "\n".join(lines)


def _render_ranking(paths: tuple[str, ...], relevant: tuple[str, ...]) -> str:
    """List returned paths, marking labeled ones '+' and the rest '-'."""
    if not paths:
        return "(no results)"
    return ", ".join(f"{'+' if path in relevant else '-'}{path}" for path in paths)


def _mean(values: Iterable[float]) -> float:
    collected = list(values)
    return sum(collected) / len(collected) if collected else 0.0


def main(argv: list[str] | None = None) -> int:
    """Print the comparison table, optionally refreshing the recorded results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"overwrite {RECORD_PATH.name} with the measured numbers",
    )
    args = parser.parse_args(argv)

    measurement = measure()
    print(format_report(measurement))
    if args.write:
        write_record(measurement)
        print(f"Wrote {RECORD_PATH.relative_to(BACKEND_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

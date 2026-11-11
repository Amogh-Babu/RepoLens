"""Reproduce the top-5 search precision measurement (issue #37, Risk 1).

These tests check that labels name files RepoLens indexes, that the grep
baseline uses the same query terms, and that keyword results remain reproducible.
The recorded BGE measurement is checked for its per-query non-regression gate
without downloading model weights during tests.

Refresh the recorded numbers deliberately, from `backend/`:

    python -m benchmarks.search_precision --write
"""

from collections.abc import Iterator
from pathlib import Path
import subprocess

import pytest

from benchmarks.search_precision import (
    GREP,
    GREP_RANKED,
    REPOLENS,
    REPOLENS_HYBRID,
    SYSTEMS,
    LabeledQuery,
    Measurement,
    RepoQuerySet,
    TrackedFilesUnavailableError,
    baseline_top_paths,
    build_search_service,
    format_report,
    list_repository_paths,
    load_query_sets,
    load_record,
    measure,
    query_terms,
    ranked_baseline_top_paths,
)
from repolens.search import SearchService
from repolens.search.embedding import HashEmbedder


TOP_K, QUERY_SETS = load_query_sets()


def _all_queries() -> list[tuple[RepoQuerySet, LabeledQuery]]:
    return [(repo, case) for repo in QUERY_SETS for case in repo.queries]


ALL_QUERIES = _all_queries()
QUERY_IDS = [f"{repo.id}:{case.query}" for repo, case in ALL_QUERIES]


@pytest.fixture(scope="module")
def measurement() -> Iterator[Measurement]:
    """Measure once with deterministic embeddings; this never downloads a model."""
    yield measure(embedder=HashEmbedder())


def test_three_repositories_are_labeled() -> None:
    assert len(QUERY_SETS) == 3
    assert {repo.id for repo in QUERY_SETS} == {
        "search_mini_repo",
        "analysis_mini_repo",
        "e2e_reference",
    }
    for repo in QUERY_SETS:
        assert repo.root.is_dir(), repo.root
        assert repo.queries, repo.id


def test_every_query_is_distinct_and_labeled() -> None:
    for repo in QUERY_SETS:
        queries = [case.query for case in repo.queries]
        assert len(set(queries)) == len(queries), repo.id
        for case in repo.queries:
            assert case.relevant, f"{repo.id}:{case.query} labels no file"
            assert len(set(case.relevant)) == len(case.relevant)
            assert case.rationale.strip(), f"{repo.id}:{case.query} has no rationale"


@pytest.mark.parametrize("repo", QUERY_SETS, ids=[repo.id for repo in QUERY_SETS])
def test_labeled_files_exist_and_are_reachable(repo: RepoQuerySet) -> None:
    """A label RepoLens cannot index, or grep cannot list, would skew the result."""
    _, indexed = build_search_service(repo.root)
    listed = list_repository_paths(repo.root)

    for case in repo.queries:
        for path in case.relevant:
            assert (repo.root / path).is_file(), f"{repo.id}:{case.query} -> {path}"
            assert path in indexed, f"{path} is not in the RepoLens index"
            assert path in listed, f"{path} is not in the grep file list"


@pytest.mark.parametrize(
    "query", [case.query for _, case in ALL_QUERIES], ids=QUERY_IDS
)
def test_the_baseline_searches_for_the_same_terms_as_repolens(query: str) -> None:
    """Fairness check: both systems must tokenize a query identically.

    `SearchService._parse_query` is private, which is the point -- reading it
    here is what keeps `benchmarks.search_precision.query_terms` honest if the
    service's tokenization ever changes.
    """
    assert query_terms(query) == SearchService._parse_query(query)


def test_the_file_list_holds_only_the_files_git_tracks(tmp_path: Path) -> None:
    """Untracked and ignored working-tree files must not reach the baseline.

    Listing the directory instead would let a `.DS_Store`, a cache, or any
    local scratch file change what grep matches and how many files it was
    given, which would make the recorded measurement depend on whose checkout
    it ran in.
    """
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    for name in ("tracked.py", "ignored.py", "untracked.py"):
        (tmp_path / name).touch()
    subprocess.run(
        ("git", "-C", str(tmp_path), "add", ".gitignore", "tracked.py"), check=True
    )

    assert list_repository_paths(tmp_path) == (".gitignore", "tracked.py")


def test_a_tree_outside_a_git_checkout_fails_loudly(tmp_path: Path) -> None:
    """Falling back to a directory walk would silently change the file set."""
    with pytest.raises(TrackedFilesUnavailableError):
        list_repository_paths(tmp_path / "not-a-checkout")


def test_the_grep_baseline_matches_terms_against_the_whole_path() -> None:
    paths = ("app/auth/login.py", "app/billing.py", "README.md")

    assert baseline_top_paths(paths, "auth", TOP_K) == ("app/auth/login.py",)
    assert baseline_top_paths(paths, "billing auth", TOP_K) == (
        "app/auth/login.py",
        "app/billing.py",
    )
    assert baseline_top_paths(paths, "nothing-here", TOP_K) == ()


def test_the_grep_baseline_keeps_the_listing_order_and_stops_at_k() -> None:
    paths = tuple(f"app/auth/file{index}.py" for index in range(TOP_K + 3))

    assert baseline_top_paths(paths, "auth", TOP_K) == paths[:TOP_K]


def test_the_ranked_grep_baseline_prefers_paths_matching_more_terms() -> None:
    paths = ("app/aaa_auth.py", "app/zzz_auth_login.py")

    assert ranked_baseline_top_paths(paths, "auth login", TOP_K) == (
        "app/zzz_auth_login.py",
        "app/aaa_auth.py",
    )


def test_every_system_returns_at_most_k_results(measurement: Measurement) -> None:
    for result in measurement.results:
        for system in SYSTEMS:
            assert len(result.rankings[system]) <= measurement.top_k
            assert len(set(result.rankings[system])) == len(result.rankings[system])


def test_hits_never_exceed_what_a_perfect_ranker_could_do(
    measurement: Measurement,
) -> None:
    for result in measurement.results:
        for system in SYSTEMS:
            assert 0 <= result.hits(system) <= result.ideal_hits
            assert 0.0 <= result.precision(system) <= result.ideal_precision


def test_keyword_measurement_matches_the_recorded_rankings(
    measurement: Measurement,
) -> None:
    """Keyword results are independent of the model used for the hybrid pass."""
    record = load_record()
    for repo in measurement.repos:
        recorded_repo = next(item for item in record["repos"] if item["id"] == repo.repo.id)
        for result in repo.results:
            recorded_result = next(
                item for item in recorded_repo["queries"] if item["query"] == result.query
            )
            assert list(result.rankings[REPOLENS]) == recorded_result["top"][REPOLENS]


def test_recorded_hybrid_meets_keyword_precision_on_every_query() -> None:
    record = load_record()

    assert record["embedding_model"] == "BAAI/bge-small-en-v1.5"
    for repo in record["repos"]:
        for result in repo["queries"]:
            assert result["hits"][REPOLENS_HYBRID] >= result["hits"][REPOLENS], (
                repo["id"],
                result["query"],
            )


def test_vague_onboarding_query_returns_labeled_files() -> None:
    record = load_record()
    repo = next(item for item in record["repos"] if item["id"] == "e2e_reference")
    result = next(
        item
        for item in repo["queries"]
        if item["query"] == "if I'm meant to work on prod, where do I start?"
    )

    assert result["hits"][REPOLENS] == 0
    assert result["hits"][REPOLENS_HYBRID] > 0


def test_the_report_names_every_system_and_its_overall_precision(
    measurement: Measurement,
) -> None:
    report = format_report(measurement)

    assert f"Top-{measurement.top_k} search precision" in report
    for system in (REPOLENS, GREP, GREP_RANKED):
        assert f"{measurement.precision(system):.3f}" in report
    for repo in measurement.repos:
        assert repo.repo.id in report
        for result in repo.results:
            assert repr(result.query) in report

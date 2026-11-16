"""Scoring and query-parsing checks for `SearchService`, written as pytest tests.

These complement the unittest-style cases in test_search_service.py; pytest runs
both. New backend tests should follow this style: plain functions, bare
`assert`, fixtures from conftest.py, and `pytest.mark.parametrize` for tables.
"""

import pytest

from repolens.search import PaginationValidationError, SearchDocument


@pytest.mark.parametrize(
    ("document", "expected_score"),
    [
        # Field weight for one matched term, plus 3 for one distinct term.
        (SearchDocument(path="src/auth.py"), 8 + 3),
        (SearchDocument(path="src/a.py", symbols=("auth",)), 6 + 3),
        (SearchDocument(path="src/a.py", references=("auth",)), 4 + 3),
        (SearchDocument(path="src/a.py", comments=("auth",)), 2 + 3),
    ],
    ids=["filename", "symbol", "reference", "comment"],
)
def test_each_field_contributes_its_weight(make_search_service, document, expected_score):
    page = make_search_service(document).search("analysis-1", "auth")

    assert page.results[0].score == expected_score


def test_query_is_case_insensitive_and_deduplicates_terms(make_search_service):
    service = make_search_service(SearchDocument(path="src/Login.py"))

    once = service.search("analysis-1", "login")
    repeated = service.search("analysis-1", "LOGIN Login login")

    assert once.results[0].score == repeated.results[0].score
    assert once.results[0].matches[0].matched_terms == ("login",)


def test_matching_dependents_add_to_score(make_search_service):
    service = make_search_service(
        SearchDocument(path="auth/core.py", depended_on_by=("auth/views.py", "other.py")),
        SearchDocument(path="auth/views.py"),
    )

    page = service.search("analysis-1", "auth")

    # Only auth/views.py matches the query, so core.py gets one 1.5-point bonus.
    assert [result.path for result in page.results] == ["auth/core.py", "auth/views.py"]
    assert page.results[0].score - page.results[1].score == 1.5


def test_repeated_mentions_do_not_outweigh_a_definition(make_search_service):
    service = make_search_service(
        SearchDocument(path="src/noisy.py", comments=("pipeline",) * 10),
        SearchDocument(path="src/core.py", symbols=("pipeline",)),
    )

    page = service.search("analysis-1", "pipeline")

    assert [result.path for result in page.results] == ["src/core.py", "src/noisy.py"]


def _goal_service(make_search_service):
    return make_search_service(
        SearchDocument(path="app/pipeline.py"),
        SearchDocument(path="tests/pipeline.py"),
        SearchDocument(path="config/pipeline.py"),
    )


@pytest.mark.parametrize(
    ("intent", "expected", "note"),
    [
        ("tests", "tests/pipeline.py", "Ranked higher: a test or example file."),
        ("configuration", "config/pipeline.py", "Ranked higher: a configuration file."),
    ],
)
def test_a_reading_goal_ranks_its_files_higher(
    make_search_service, intent, expected, note
):
    page = _goal_service(make_search_service).search(
        "analysis-1", "pipeline", intent=intent, limit=1
    )

    assert page.results[0].path == expected
    assert page.results[0].reason.endswith(note)
    assert len(page.matched_paths) == 3


def test_the_implementation_goal_ranks_tests_and_config_lower(make_search_service):
    page = _goal_service(make_search_service).search(
        "analysis-1", "pipeline", intent="implementation"
    )
    by_path = {result.path: result for result in page.results}

    assert max(page.results, key=lambda result: result.score).path == "app/pipeline.py"
    # Only the files the goal moved say so.
    assert "Ranked" not in by_path["app/pipeline.py"].reason
    assert by_path["tests/pipeline.py"].reason.endswith(
        "Ranked lower: a test or example file."
    )
    assert by_path["config/pipeline.py"].reason.endswith(
        "Ranked lower: a configuration file."
    )


def test_no_reading_goal_leaves_scores_and_reasons_alone(make_search_service):
    page = _goal_service(make_search_service).search("analysis-1", "pipeline")

    assert len({result.score for result in page.results}) == 1
    assert all("Ranked" not in result.reason for result in page.results)


@pytest.mark.parametrize("bad_value", [True, 1.0, "1"])
def test_pagination_rejects_non_integers(make_search_service, bad_value):
    service = make_search_service(SearchDocument(path="auth.py"))

    with pytest.raises(PaginationValidationError):
        service.search("analysis-1", "auth", limit=bad_value)

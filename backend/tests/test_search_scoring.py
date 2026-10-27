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


@pytest.mark.parametrize("bad_value", [True, 1.0, "1"])
def test_pagination_rejects_non_integers(make_search_service, bad_value):
    service = make_search_service(SearchDocument(path="auth.py"))

    with pytest.raises(PaginationValidationError):
        service.search("analysis-1", "auth", limit=bad_value)

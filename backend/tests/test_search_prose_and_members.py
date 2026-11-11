"""Search over docstrings, comments, and class members (#77, part 1)."""

import time

import pytest
from fastapi.testclient import TestClient

from repolens.api.app import create_app
from repolens.graph import (
    AnalysisRecord,
    AnalyzedFile,
    CommentRecord,
    MemberRecord,
    SqliteGraphStore,
    SymbolRecord,
)
from repolens.search import SearchDocument, SearchService


@pytest.mark.parametrize(
    ("document", "expected_score"),
    [
        # Field weight for one matched term, plus 3 for one distinct term.
        (SearchDocument(path="src/a.py", members=("User.auth",)), 5 + 3),
        (SearchDocument(path="src/a.py", docstrings=("Handles auth.",)), 3 + 3),
    ],
    ids=["member", "docstring"],
)
def test_members_and_docstrings_contribute_their_weight(
    make_search_service, document, expected_score
):
    page = make_search_service(document).search("analysis-1", "auth")

    assert page.results[0].score == expected_score
    assert page.results[0].matches[0].kind in {"member", "docstring"}


def test_members_rank_below_module_level_symbols(make_search_service):
    service = make_search_service(
        SearchDocument(path="a.py", members=("Cart.checkout",)),
        SearchDocument(path="b.py", symbols=("checkout",)),
    )

    ranked = service.search("analysis-1", "checkout").results

    assert [result.path for result in ranked] == ["b.py", "a.py"]


def test_prose_terms_must_start_a_word(make_search_service):
    service = make_search_service(
        SearchDocument(path="a.py", docstrings=("Authenticate the user.",)),
        SearchDocument(path="b.py", comments=("Reauthorize later.",)),
        SearchDocument(path="c.py", docstrings=("Read the tax_rate setting.",)),
    )

    assert [r.path for r in service.search("analysis-1", "auth").results] == ["a.py"]
    assert [r.path for r in service.search("analysis-1", "rate").results] == ["c.py"]


def test_stop_words_and_single_letters_do_not_match_prose(make_search_service):
    service = make_search_service(
        SearchDocument(path="a.py", docstrings=("Where the work starts in this module.",)),
    )

    assert service.search("analysis-1", "where do i the").results == ()
    assert [r.path for r in service.search("analysis-1", "where do i work").results] == [
        "a.py"
    ]


def test_a_question_searches_only_its_topic_words(make_search_service):
    service = make_search_service(
        SearchDocument(path="src/itsdangerous/timed.py", symbols=("SignatureExpired",)),
        SearchDocument(path="src/itsdangerous/encoding.py", symbols=("want_bytes",)),
        SearchDocument(path="docs/conf.py", symbols=("copyright",)),
    )

    results = service.search("analysis-1", "where do I check if a signature expired").results

    assert [r.path for r in results] == ["src/itsdangerous/timed.py"]
    assert results[0].matches[0].matched_terms == ("signature", "expired")


def test_a_query_of_only_stop_words_is_searched_as_written(make_search_service):
    service = make_search_service(SearchDocument(path="app/where.py"), SearchDocument(path="io.py"))

    assert [r.path for r in service.search("analysis-1", "where").results] == [
        "app/where.py"
    ]
    assert [r.path for r in service.search("analysis-1", "do").results] == []
    assert service.search("analysis-1", "a").total == 1


def _store_with_one_file() -> tuple[SqliteGraphStore, str]:
    store = SqliteGraphStore()
    long_docstring = (
        "Background. " * 20
        + "This module computes the checkout total for a cart. "
        + "Trailing notes. " * 20
    )
    store.save(
        AnalysisRecord(
            analysis_id="analysis-1",
            repo="https://github.com/acme/shop",
            sha="a" * 40,
            created_at=time.time(),
            files=(
                AnalyzedFile(
                    path="shop/orders.py",
                    line_count=40,
                    symbols=(SymbolRecord(name="Order", kind="class", line=3),),
                    members=(
                        MemberRecord(owner="Order", name="checkout", kind="method", line=9),
                        MemberRecord(owner="Order", name="items", kind="attribute", line=5),
                    ),
                    comments=(
                        CommentRecord(line=1, text=long_docstring, kind="docstring"),
                        CommentRecord(line=8, text="Refunds go through checkout too."),
                    ),
                ),
            ),
        )
    )
    return store, "analysis-1"


def test_the_store_serves_members_docstrings_and_comments_to_search() -> None:
    store, analysis_id = _store_with_one_file()

    (document,) = store.get_search_documents(analysis_id)

    assert document.members == ("Order.checkout", "Order.items")
    assert document.comments == ("Refunds go through checkout too.",)
    assert len(document.docstrings) == 1
    assert store.get_file_match_lines(analysis_id, "shop/orders.py") == {
        ("symbol", "Order"): 3,
        ("member", "Order.checkout"): 9,
        ("member", "Order.items"): 5,
        ("docstring", document.docstrings[0]): 1,
        ("comment", "Refunds go through checkout too."): 8,
    }


def test_members_stay_out_of_the_file_detail_symbols() -> None:
    store, analysis_id = _store_with_one_file()

    detail = store.get_file(analysis_id, "shop/orders.py")

    assert [symbol.name for symbol in detail.symbols] == ["Order"]


def test_the_api_keeps_four_match_kinds_and_shortens_long_prose() -> None:
    store, analysis_id = _store_with_one_file()
    client = TestClient(create_app(store))

    response = client.get(f"/analyses/{analysis_id}/search", params={"q": "checkout"})

    assert response.status_code == 200
    matches = {
        (match["kind"], match["line"]): match for match in response.json()["results"][0]["matches"]
    }
    assert set(matches) == {("symbol", 9), ("comment", 1), ("comment", 8)}
    assert matches[("symbol", 9)]["text"] == "Order.checkout"

    docstring = matches[("comment", 1)]
    assert len(docstring["text"]) <= 122
    assert "checkout total" in docstring["text"]
    assert docstring["text"].startswith("…") and docstring["text"].endswith("…")
    assert len(docstring["value"]) > len(docstring["text"])

    assert matches[("comment", 8)]["text"] == "Refunds go through checkout too."


def test_search_service_reads_the_new_fields_from_the_graph_store() -> None:
    store, analysis_id = _store_with_one_file()

    page = SearchService(store).search(analysis_id, "items")

    assert [match.kind for match in page.results[0].matches] == ["member"]

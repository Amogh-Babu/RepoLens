"""Structural verification of model answers against source and graph."""

import pytest

from repolens.ai.context import build_context
from repolens.ai.validation import validate_summary
from repolens.analysis import AnalysisService

from tests.ai_fixture import ANALYSIS_ID, AUTH_SOURCE, good_auth_answer, seed_store


def _context(budget: int = 40_000):
    store = seed_store()
    return build_context(
        detail=store.get_file(ANALYSIS_ID, "app/auth.py"),
        parsed=AnalysisService().analyze_source("app/auth.py", AUTH_SOURCE),
        source=AUTH_SOURCE,
        max_input_chars=budget,
    )


def _problems(answer, budget: int = 40_000) -> tuple[str, ...]:
    result = validate_summary(answer, _context(budget))
    assert result.ok is (not result.problems)
    return result.problems


def test_a_correct_answer_is_accepted_as_is() -> None:
    result = validate_summary(good_auth_answer(), _context())

    assert result.ok
    assert result.summary is not None
    assert result.summary.key_symbols[0].name == "sign"
    assert result.summary.model_dump(by_alias=True)["keySymbols"][0]["line"] == 7


def test_an_accurate_summary_needs_no_docstrings() -> None:
    # AUTH_SOURCE has no docstrings or comments; the answer is built from code.
    assert '"""' not in AUTH_SOURCE and "#" not in AUTH_SOURCE
    assert _problems(good_auth_answer()) == ()


def test_a_hallucinated_function_is_rejected() -> None:
    answer = good_auth_answer(
        keySymbols=[{"name": "refresh_token", "kind": "function", "description": "x", "line": 30}]
    )

    assert _problems(answer) == (
        "keySymbols 'refresh_token' is not defined in this file's syntax tree.",
    )


def test_a_real_symbol_with_the_wrong_kind_or_line_is_rejected() -> None:
    wrong_kind = good_auth_answer(
        keySymbols=[{"name": "Sessions", "kind": "function", "description": "x", "line": 22}]
    )
    wrong_line = good_auth_answer(
        keySymbols=[{"name": "check", "kind": "function", "description": "x", "line": 15}]
    )

    assert _problems(wrong_kind) == ("keySymbols 'Sessions' is a class, not a function.",)
    assert _problems(wrong_line) == ("keySymbols 'check' is defined on line 14, not line 15.",)


def test_a_hallucinated_dependency_is_rejected() -> None:
    invented = good_auth_answer(
        dependencies=[{"path": "app/database.py", "relationship": "imports", "description": "x"}]
    )
    reversed_edge = good_auth_answer(
        dependencies=[{"path": "main.py", "relationship": "imports", "description": "x"}]
    )
    external = good_auth_answer(
        dependencies=[{"path": "hmac", "relationship": "imports", "description": "x"}]
    )

    assert _problems(invented) == (
        "dependencies 'app/database.py' is not an internal dependency in the analyzed graph.",
    )
    assert _problems(reversed_edge) == (
        "dependencies 'main.py' has relationship 'importedBy', not 'imports'.",
    )
    assert _problems(external)


@pytest.mark.parametrize(
    "evidence, problem",
    [
        ({"startLine": 20, "endLine": 40, "description": "x"}, "past the end of the file"),
        ({"startLine": 9, "endLine": 7, "description": "x"}, "starts after it ends"),
        ({"startLine": 0, "endLine": 3, "description": "x"}, "greater than or equal to 1"),
    ],
)
def test_invalid_evidence_lines_are_rejected(evidence, problem) -> None:
    problems = _problems(good_auth_answer(evidence=[evidence]))

    assert any(problem in item for item in problems), problems


def test_side_effects_need_valid_line_ranges_too() -> None:
    answer = good_auth_answer(
        sideEffects=[{"kind": "network", "description": "x", "startLine": 90, "endLine": 91}]
    )

    assert any("sideEffects range 90-91" in item for item in _problems(answer))


def test_citations_of_lines_that_were_not_sent_are_rejected() -> None:
    context = _context(budget=600)
    assert context.coverage == "partial"
    sent = {
        line for start, end in context.inspected_lines for line in range(start, end + 1)
    }
    missing = min(set(range(1, context.line_count + 1)) - sent)
    answer = good_auth_answer(
        coverage="partial",
        keySymbols=[],
        evidence=[{"startLine": missing, "endLine": missing, "description": "x"}],
        responsibilities=["Signs tokens."],
    )

    problems = validate_summary(answer, context).problems

    assert any("not provided" in item for item in problems), problems


def test_a_partial_file_cannot_be_called_complete() -> None:
    context = _context(budget=600)
    answer = good_auth_answer(
        keySymbols=[], evidence=[{"startLine": 1, "endLine": 2, "description": "x"}]
    )

    problems = validate_summary(answer, context).problems

    assert any("coverage is 'complete'" in item for item in problems)


def test_partial_coverage_is_recorded_from_the_request_not_the_model() -> None:
    answer = good_auth_answer(coverage="partial")

    result = validate_summary(answer, _context())

    assert result.ok and result.summary is not None
    assert result.summary.coverage == "complete"


def test_backticked_code_names_must_exist_in_the_source() -> None:
    answer = good_auth_answer(summary="Signs tokens with `jwt.encode` and checks them.")

    assert _problems(answer) == (
        "The summary mentions `jwt.encode`, but 'jwt' does not appear in the inspected source.",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"summary": "x" * 401},
        {"responsibilities": []},
        {"responsibilities": ["a"] * 6},
        {"evidence": []},
        {"coverage": "mostly"},
        {"keySymbols": [{"name": "sign", "kind": "function", "line": 7}]},
        {"extra": "field"},
    ],
)
def test_schema_violations_and_oversized_fields_are_rejected(overrides) -> None:
    assert _problems(good_auth_answer(**overrides))


def test_unparseable_output_is_rejected() -> None:
    assert _problems({"_unparseable": True})
    assert _problems("not a dict")

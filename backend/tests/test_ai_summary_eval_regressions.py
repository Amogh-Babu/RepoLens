"""Regressions from the first live AI-summary evaluation."""

from benchmarks.ai_summary_eval import (
    CaseResult,
    _score_text,
    evaluate_summary,
    load_expected,
)


def test_explicitly_refuted_docstring_is_not_an_asserted_claim():
    case = load_expected()["files"]["notes_app/cache.py"]
    result = CaseResult(path="notes_app/cache.py")
    _score_text(
        result,
        "The docstring says this is an in-memory cache, but the implementation "
        "actually writes and deletes files on disk.",
        case,
    )
    assert "in-memory cache" not in result.forbidden_hits


def test_unrefuted_false_claim_is_still_rejected():
    case = load_expected()["files"]["notes_app/cache.py"]
    result = CaseResult(path="notes_app/cache.py")
    _score_text(result, "This is an in-memory cache. Nothing is written.", case)
    assert "in-memory cache" in result.forbidden_hits
    assert "nothing is written" in result.forbidden_hits


def test_contradiction_wording_accepts_implementation_contrast():
    case = load_expected()["files"]["notes_app/cache.py"]
    summary = {
        "uncertainties": [
            "The module docstring says nothing is written to disk, "
            "but the implementation clearly writes and deletes files."
        ],
        "coverage": "complete", "keySymbols": [],
        "dependencies": [], "sideEffects": [],
    }
    assert evaluate_summary("notes_app/cache.py", summary, case).contradiction_flagged is True


def test_source_backed_delegated_effects_are_allowed():
    case = load_expected()["files"]["notes_app/service.py"]
    summary = {
        "coverage": "complete", "keySymbols": [], "dependencies": [],
        "sideEffects": [
            {"kind": "database", "startLine": 22, "endLine": 22},
            {"kind": "other", "startLine": 23, "endLine": 23},
            {"kind": "other", "startLine": 30, "endLine": 32},
            {"kind": "other", "startLine": 34, "endLine": 34},
        ],
    }
    assert evaluate_summary("notes_app/service.py", summary, case).unexpected_side_effects == []


def test_unsupported_or_wrongly_cited_effects_are_rejected():
    case = load_expected()["files"]["notes_app/service.py"]
    summary = {
        "coverage": "complete", "keySymbols": [], "dependencies": [],
        "sideEffects": [
            {"kind": "network", "startLine": 22, "endLine": 22},
            {"kind": "database", "startLine": 13, "endLine": 13},
        ],
    }
    assert evaluate_summary("notes_app/service.py", summary, case).unexpected_side_effects == [
        "database", "network"
    ]


def test_auth_environment_effect_is_still_unexpected():
    case = load_expected()["files"]["notes_app/auth.py"]
    summary = {
        "coverage": "complete", "keySymbols": [], "dependencies": [],
        "sideEffects": [{"kind": "environment", "startLine": 1, "endLine": 1}],
    }
    assert evaluate_summary("notes_app/auth.py", summary, case).unexpected_side_effects == [
        "environment"
    ]

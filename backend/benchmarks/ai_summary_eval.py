"""Evaluate AI file summaries against hand-verified expectations.

Structural validation (`repolens.ai.validation`) proves that a summary names
only real symbols, real dependencies, and real line ranges. It cannot tell
whether the prose is right. This harness checks that second part on the
reference repository in `tests/fixtures/ai_reference`, whose `expected.json`
was written by hand from the source: for each file, the behaviors an accurate
summary must mention, the symbols and dependencies it should name, the side
effects it should report, and the claims it must not make (a parroted
misleading docstring, an obeyed prompt injection).

The checks are keyword-based, so they are a floor, not a proof: a summary can
pass them and still be subtly wrong, and that is why summaries are labelled
as AI-generated and carry evidence links.

Run it from `backend/`:

    python -m benchmarks.ai_summary_eval            # scripted answers + baseline
    python -m benchmarks.ai_summary_eval --live     # the configured real model

`--live` sends the fixture files to the configured provider and needs
`REPOLENS_AI_ENABLED=true` and `OPENAI_API_KEY`. Nothing here records results
to a file: live numbers are only meaningful when someone runs them.
"""

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any

from repolens.ai import AiConfig, CodeSummaryService
from repolens.ai.errors import SummaryError
from repolens.ai.models import CodeSummaryContext, ProviderResult
from repolens.ai.source import validate_repo_path
from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files
from repolens.graph import AnalysisRecord, SqliteGraphStore
from repolens.onboarding.service import _summary as deterministic_summary


BACKEND_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = BACKEND_ROOT / "tests" / "fixtures" / "ai_reference"
REPO_DIR = FIXTURE_DIR / "repo"
ANALYSIS_ID = "analysis-aieval000001"
SHA = "a1" * 20

# Small enough that `big_report.py` is only partly sent, as `expected.json` assumes.
EVAL_MAX_INPUT_CHARS = 2_000


def load_expected() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))


def load_answers() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / "answers.json").read_text(encoding="utf-8"))


def build_store(repo_url: str) -> SqliteGraphStore:
    """Analyze the fixture through the production path into an in-memory store."""
    analysis = AnalysisService().analyze_repository(REPO_DIR)
    store = SqliteGraphStore()
    store.save(
        AnalysisRecord(
            analysis_id=ANALYSIS_ID,
            repo=repo_url,
            sha=SHA,
            status="completed",
            files=classify_imports(to_analyzed_files(analysis)),
            embeddings=(),
        )
    )
    return store


class FixtureSourceFetcher:
    """A `SourceFetcher` that reads the fixture tree instead of GitHub."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str]] = []

    def fetch(self, repo_url: str, sha: str, path: str) -> str:
        self.requests.append((repo_url, sha, path))
        safe = validate_repo_path(path)
        return (REPO_DIR / safe).read_text(encoding="utf-8")


class ScriptedProvider:
    """A provider that answers from `answers.json`; no network."""

    def __init__(self, answers: Mapping[str, Mapping[str, Any]]) -> None:
        self._answers = answers
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def summarize(
        self, context: CodeSummaryContext, repair_feedback: tuple[str, ...] = ()
    ) -> ProviderResult:
        self.calls.append((context.path, repair_feedback))
        return ProviderResult(payload=dict(self._answers[context.path]), model="scripted")


def patched_answers(bad_case: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the good answers with one file's answer replaced by a bad variant."""
    answers = load_answers()["good"]
    path = bad_case["path"]
    return {**answers, path: {**answers[path], **bad_case["patch"]}}


@dataclass
class CaseResult:
    """How one summary measured up to its expectations."""

    path: str
    behaviors_hit: int = 0
    behaviors_total: int = 0
    missing_behaviors: list[list[str]] = field(default_factory=list)
    missing_symbols: list[str] = field(default_factory=list)
    missing_dependencies: list[list[str]] = field(default_factory=list)
    missing_side_effects: list[str] = field(default_factory=list)
    unexpected_side_effects: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)
    contradiction_flagged: bool | None = None
    coverage_ok: bool = True
    error: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.error is None
            and not self.missing_behaviors
            and not self.missing_symbols
            and not self.missing_dependencies
            and not self.missing_side_effects
            and not self.unexpected_side_effects
            and not self.forbidden_hits
            and self.contradiction_flagged is not False
            and self.coverage_ok
        )


def _claims_text(summary: Mapping[str, Any]) -> str:
    """Text making positive claims (uncertainties are excluded on purpose)."""
    parts = [summary.get("summary", ""), summary.get("purpose", "")]
    parts += list(summary.get("responsibilities", []))
    for key in ("keySymbols", "dependencies", "sideEffects", "evidence"):
        parts += [item.get("description", "") for item in summary.get(key, [])]
    parts += [item.get("name", "") for item in summary.get("keySymbols", [])]
    parts += [item.get("path", "") for item in summary.get("dependencies", [])]
    return " ".join(parts).casefold()


def _score_text(result: CaseResult, text: str, case: Mapping[str, Any]) -> None:
    folded = text.casefold()
    groups = case["behaviors"]
    result.behaviors_total = len(groups)
    for group in groups:
        if any(word.casefold() in folded for word in group):
            result.behaviors_hit += 1
        else:
            result.missing_behaviors.append(group)
    result.forbidden_hits = [phrase for phrase in case["forbidden"] if phrase.casefold() in folded]


def evaluate_summary(path: str, summary: Mapping[str, Any], case: Mapping[str, Any]) -> CaseResult:
    """Score a structured summary (the API's `summary` object) for one file."""
    result = CaseResult(path=path)
    _score_text(result, _claims_text(summary), case)
    named = {item["name"] for item in summary.get("keySymbols", [])}
    result.missing_symbols = [name for name in case["keySymbols"] if name not in named]
    listed = {(item["path"], item["relationship"]) for item in summary.get("dependencies", [])}
    result.missing_dependencies = [
        list(dep) for dep in case["dependencies"] if tuple(dep) not in listed
    ]
    reported = {item["kind"] for item in summary.get("sideEffects", [])}
    expected = set(case["sideEffectKinds"])
    result.missing_side_effects = sorted(expected - reported)
    result.unexpected_side_effects = sorted(reported - expected)
    if case["mustFlagContradiction"]:
        uncertainties = " ".join(summary.get("uncertainties", [])).casefold()
        result.contradiction_flagged = "docstring" in uncertainties and any(
            word in uncertainties for word in ("contradict", "but the code", "does not match")
        )
    wanted = case.get("coverageUnderTestBudget", "complete")
    result.coverage_ok = summary.get("coverage") == wanted
    return result


def evaluate_text_only(path: str, text: str, case: Mapping[str, Any]) -> CaseResult:
    """Score a plain one-line description (the deterministic baseline)."""
    result = CaseResult(path=path)
    _score_text(result, text, case)
    return result


def deterministic_baseline(store: SqliteGraphStore) -> dict[str, str]:
    """Return the overview's existing deterministic description of every file."""
    graph = store.get_graph(ANALYSIS_ID)
    documents = {doc.path: doc for doc in store.get_search_documents(ANALYSIS_ID)}
    dependents: dict[str, set[str]] = {node.path: set() for node in graph.files}
    for edge in graph.edges:
        dependents[edge.target].add(edge.source)
    return {path: deterministic_summary(path, documents, dependents) for path in dependents}


def run_service(
    service_factory: Callable[[SqliteGraphStore], CodeSummaryService],
) -> tuple[dict[str, CaseResult], dict[str, CaseResult]]:
    """Summarize every expected file and score AI and baseline descriptions."""
    expected = load_expected()
    store = build_store(expected["repoUrl"])
    service = service_factory(store)
    baseline = deterministic_baseline(store)
    ai_results: dict[str, CaseResult] = {}
    baseline_results: dict[str, CaseResult] = {}
    for path, case in expected["files"].items():
        baseline_results[path] = evaluate_text_only(path, baseline[path], case)
        try:
            payload = service.generate_summary(ANALYSIS_ID, path)
        except SummaryError as error:
            ai_results[path] = CaseResult(path=path, error=f"{error.code}: {error.message}")
            continue
        ai_results[path] = evaluate_summary(path, payload["summary"], case)
    return ai_results, baseline_results


def _table(ai: Mapping[str, CaseResult], baseline: Mapping[str, CaseResult]) -> str:
    rows = ["| file | AI behaviors | AI pass | baseline behaviors | baseline pass |", "| --- | ---: | :---: | ---: | :---: |"]
    for path, result in ai.items():
        base = baseline[path]
        rows.append(
            f"| `{path}` | {result.behaviors_hit}/{result.behaviors_total} | "
            f"{'yes' if result.passed else 'no'} | {base.behaviors_hit}/{base.behaviors_total} | "
            f"{'yes' if base.passed else 'no'} |"
        )
    passed = sum(result.passed for result in ai.values())
    base_passed = sum(result.passed for result in baseline.values())
    rows.append(f"| **total** | | **{passed}/{len(ai)}** | | **{base_passed}/{len(baseline)}** |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="Summarize with the configured real provider (sends fixture source to it).",
    )
    args = parser.parse_args(argv)

    if args.live:
        config = AiConfig.from_environment()
        if not config.active:
            print("--live needs REPOLENS_AI_ENABLED=true and OPENAI_API_KEY.", file=sys.stderr)
            return 2
        live_config = AiConfig(
            **{**config.__dict__, "max_input_chars": EVAL_MAX_INPUT_CHARS}
        )

        def factory(store: SqliteGraphStore) -> CodeSummaryService:
            return CodeSummaryService(store, live_config, fetcher=FixtureSourceFetcher())

        label = f"live model {live_config.model}"
    else:
        answers = load_answers()["good"]

        def factory(store: SqliteGraphStore) -> CodeSummaryService:
            config = AiConfig(enabled=True, api_key="offline", max_input_chars=EVAL_MAX_INPUT_CHARS)
            return CodeSummaryService(
                store, config, provider=ScriptedProvider(answers), fetcher=FixtureSourceFetcher()
            )

        label = "scripted answers (NOT a real model)"

    ai, baseline = run_service(factory)
    print(f"AI summaries: {label}\n")
    print(_table(ai, baseline))
    for path, result in ai.items():
        if not result.passed:
            print(f"\n{path}: {json.dumps(result.__dict__, default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

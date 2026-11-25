"""Evaluate AI search overviews on the labeled search queries.

Structural validation (`repolens.ai.search_validation`) proves that an
overview recommends only real search results and names only real symbols.
This harness measures the part it cannot prove: whether the file the
overview says to open first is one a developer would actually need. It uses
the hand-labeled queries in `labeled_queries.json` (the same ones the search
precision benchmark uses) and reports, per query:

- whether the overview passed verification, and whether it needed a repair;
- whether `startHere` is a labeled relevant file;
- how many `readNext` files are labeled relevant;
- tokens used (and an estimated cost when `REPOLENS_AI_INPUT_COST_PER_MILLION`
  and `REPOLENS_AI_OUTPUT_COST_PER_MILLION` are set).

The scripted mode (the default) answers "start with the first result, then
read the next two", which is what the reading list alone suggests. It is the
baseline a live model should beat, and it runs offline.

Run it from `backend/`:

    python -m benchmarks.ai_search_overview_eval            # scripted baseline
    python -m benchmarks.ai_search_overview_eval --live     # the configured model

`--live` sends file names, symbol names and docstring lines of the fixture
repositories to the configured provider and costs money. It needs
`REPOLENS_AI_ENABLED=true` and `OPENAI_API_KEY`. Search uses the offline hash
embedder here, so rankings can differ slightly from the BGE numbers in
`benchmarks/README.md`.
"""

import argparse
from dataclasses import dataclass, field
import sys
from typing import Any

from repolens.ai import AiConfig, CodeSummaryService, SearchOverviewService
from repolens.ai.errors import SummaryError
from repolens.ai.models import ProviderResult, ProviderUsage
from repolens.ai.search_models import SearchOverviewContext
from repolens.ai.search_provider import OpenAISearchOverviewProvider, SearchOverviewProvider
from repolens.analysis import AnalysisService, classify_imports, to_analyzed_files
from repolens.graph import AnalysisRecord, SqliteGraphStore
from repolens.search.embedding import HashEmbedder

from benchmarks.search_precision import load_query_sets


_SHA = "5e" * 20
_REPO_URL = "https://github.com/repolens-benchmarks/search-overview"


class ScriptedSearchProvider:
    """Answers with the reading list's own order; no network."""

    def overview(
        self, context: SearchOverviewContext, repair_feedback: tuple[str, ...] = ()
    ) -> ProviderResult:
        first, *rest = context.files
        return ProviderResult(
            payload={
                "summary": f"The closest match for the query is `{first.path}`.",
                "startHere": {"path": first.path, "reason": "It is ranked first."},
                "readNext": [
                    {"path": item.path, "reason": "It is ranked next."} for item in rest[:2]
                ],
                "uncertainties": [],
            },
            model="scripted",
            usage=ProviderUsage(),
        )


class NoFileSummaries:
    """A file summary provider for runs that must never summarize a file."""

    def summarize(self, context: Any, repair_feedback: tuple[str, ...] = ()) -> ProviderResult:
        raise AssertionError("The search overview eval does not summarize files.")


class CountingProvider:
    """Wraps a provider to count calls and tokens for one query."""

    def __init__(self, inner: SearchOverviewProvider) -> None:
        self.inner = inner
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def overview(
        self, context: SearchOverviewContext, repair_feedback: tuple[str, ...] = ()
    ) -> ProviderResult:
        self.calls += 1
        result = self.inner.overview(context, repair_feedback)
        self.input_tokens += result.usage.input_tokens or 0
        self.output_tokens += result.usage.output_tokens or 0
        return result


@dataclass
class QueryOutcome:
    repo: str
    query: str
    verified: bool = False
    repaired: bool = False
    start_relevant: bool = False
    next_relevant: int = 0
    next_total: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    start_here: str | None = None
    relevant: tuple[str, ...] = field(default_factory=tuple)


def _store(root: Any, analysis_id: str) -> SqliteGraphStore:
    analysis = AnalysisService().analyze_repository(root)
    store = SqliteGraphStore(embedder=HashEmbedder())
    store.save(
        AnalysisRecord(
            analysis_id=analysis_id,
            repo=_REPO_URL,
            sha=_SHA,
            status="completed",
            files=classify_imports(to_analyzed_files(analysis)),
        )
    )
    return store


def run(config: AiConfig, make_provider: Any) -> list[QueryOutcome]:
    """Generate one overview per labeled query and score it."""
    _, repos = load_query_sets()
    outcomes = []
    for index, repo in enumerate(repos):
        analysis_id = f"analysis-ovreval{index:05d}"
        store = _store(repo.root, analysis_id)
        summaries = CodeSummaryService(store, config, provider=NoFileSummaries())
        for case in repo.queries:
            provider = CountingProvider(make_provider())
            service = SearchOverviewService(store, summaries, provider=provider)
            outcome = QueryOutcome(repo=repo.id, query=case.query, relevant=case.relevant)
            try:
                payload = service.generate_overview(analysis_id, case.query, None)
            except SummaryError as error:
                outcome.error = error.code
            else:
                overview = payload["overview"]
                if overview is None:
                    outcome.error = payload["status"]
                else:
                    outcome.verified = True
                    outcome.start_here = overview["startHere"]["path"]
                    outcome.start_relevant = outcome.start_here in case.relevant
                    outcome.next_total = len(overview["readNext"])
                    outcome.next_relevant = sum(
                        step["path"] in case.relevant for step in overview["readNext"]
                    )
            outcome.repaired = provider.calls > 1
            outcome.input_tokens = provider.input_tokens
            outcome.output_tokens = provider.output_tokens
            outcomes.append(outcome)
    return outcomes


def _cost(config: AiConfig, input_tokens: int, output_tokens: int) -> str:
    if config.input_cost_per_million is None or config.output_cost_per_million is None:
        return "n/a (set REPOLENS_AI_*_COST_PER_MILLION)"
    usd = (
        input_tokens * config.input_cost_per_million
        + output_tokens * config.output_cost_per_million
    ) / 1_000_000
    return f"${usd:.4f}"


def report(outcomes: list[QueryOutcome], config: AiConfig, label: str) -> str:
    rows = [
        f"AI search overviews: {label}",
        "",
        "| repository | query | verified | repaired | start here | relevant? | read next relevant |",
        "| --- | --- | :-: | :-: | --- | :-: | :-: |",
    ]
    for item in outcomes:
        rows.append(
            f"| `{item.repo}` | {item.query} | {'yes' if item.verified else item.error} | "
            f"{'yes' if item.repaired else 'no'} | `{item.start_here or '-'}` | "
            f"{'yes' if item.start_relevant else 'no'} | {item.next_relevant}/{item.next_total} |"
        )
    total = len(outcomes)
    verified = sum(item.verified for item in outcomes)
    start = sum(item.start_relevant for item in outcomes)
    input_tokens = sum(item.input_tokens for item in outcomes)
    output_tokens = sum(item.output_tokens for item in outcomes)
    no_results = sum(item.error == "noResults" for item in outcomes)
    answered = total - no_results
    rows += [
        "",
        f"Searches with results: {answered}/{total} (no overview is offered without results).",
        f"Verified: {verified}/{answered}. Repaired: {sum(item.repaired for item in outcomes)}.",
        f"Start here is a labeled relevant file: {start}/{answered}.",
        f"Tokens: {input_tokens} in, {output_tokens} out "
        f"(about {input_tokens // max(1, total)} in per overview). "
        f"Estimated cost: {_cost(config, input_tokens, output_tokens)}.",
    ]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the configured real model (costs money; sends names and docstrings).",
    )
    args = parser.parse_args(argv)

    if args.live:
        config = AiConfig.from_environment()
        if not config.active:
            print("--live needs REPOLENS_AI_ENABLED=true and OPENAI_API_KEY.", file=sys.stderr)
            return 2
        config = AiConfig(**{**config.__dict__, "daily_call_limit": 10_000, "client_hourly_limit": 0})
        outcomes = run(config, lambda: OpenAISearchOverviewProvider(config))
        label = f"live model {config.model}"
    else:
        config = AiConfig(enabled=True, api_key="offline", daily_call_limit=10_000)
        outcomes = run(config, ScriptedSearchProvider)
        label = "scripted reading-list baseline (NOT a real model)"

    print(report(outcomes, config, label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

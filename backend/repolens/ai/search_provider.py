"""Model provider for AI search overviews.

`SearchOverviewProvider` is the seam tests replace with a fake.
`OpenAISearchOverviewProvider` sends one Structured Outputs request through
the same helper and the same model as file summaries (`call_structured`),
so both features behave alike and fail with the same errors.
"""

from typing import Any, Protocol

from repolens.ai.config import AiConfig
from repolens.ai.models import ProviderResult
from repolens.ai.provider import build_openai_client, call_structured, strict_output_schema
from repolens.ai.search_models import SearchOverview, SearchOverviewContext
from repolens.ai.search_prompts import SEARCH_INSTRUCTIONS, build_search_input


SEARCH_SCHEMA_NAME = "repolens_search_overview"

# Overviews are a few sentences; this is generous and still caps cost.
_MAX_OUTPUT_TOKENS = 1200

SEARCH_TASK = "write an overview of these search results"
SEARCH_FALLBACK = "The reading list still works."


class SearchOverviewProvider(Protocol):
    """Turns a search's context into a raw structured overview."""

    def overview(
        self,
        context: SearchOverviewContext,
        repair_feedback: tuple[str, ...] = (),
    ) -> ProviderResult:
        """Return the model's answer for `context`.

        Raises:
          ProviderTimeoutError: The provider did not answer in time.
          ProviderUnavailableError: The provider failed or refused.
        """
        ...


def build_search_request(
    config: AiConfig,
    context: SearchOverviewContext,
    repair_feedback: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the keyword arguments for `client.responses.create`."""
    request: dict[str, Any] = {
        "model": config.model,
        "instructions": SEARCH_INSTRUCTIONS,
        "input": build_search_input(context, repair_feedback),
        "text": {
            "format": {
                "type": "json_schema",
                "name": SEARCH_SCHEMA_NAME,
                "schema": strict_output_schema(SearchOverview),
                "strict": True,
            }
        },
        "max_output_tokens": min(config.max_output_tokens, _MAX_OUTPUT_TOKENS),
        "store": False,
    }
    if config.reasoning_effort:
        request["reasoning"] = {"effort": config.reasoning_effort}
    return request


class OpenAISearchOverviewProvider:
    """Write search overviews with the OpenAI Responses API."""

    def __init__(self, config: AiConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client if client is not None else build_openai_client(config)

    def overview(
        self,
        context: SearchOverviewContext,
        repair_feedback: tuple[str, ...] = (),
    ) -> ProviderResult:
        return call_structured(
            self._client,
            self._config,
            build_search_request(self._config, context, repair_feedback),
            task=SEARCH_TASK,
            noun="overview",
            fallback=SEARCH_FALLBACK,
        )

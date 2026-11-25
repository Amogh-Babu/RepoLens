"""Model providers for AI file summaries (and the shared OpenAI call).

`CodeSummaryProvider` is the seam: the service only ever calls `summarize`,
so tests inject a fake provider and never touch the network.
`OpenAICodeSummaryProvider` calls the OpenAI Responses API with Structured
Outputs (a strict JSON schema derived from `CodeSummary`). It sends only the
parameters the installed SDK's `responses.create` accepts, and no sampling
controls such as `temperature`, which some models reject.

`build_openai_client` and `call_structured` are shared with the search
overview provider (`repolens.ai.search_provider`), so both features make the
same kind of request and turn SDK failures into the same errors.

Nothing here logs the request body, the source, or the API key.
"""

import copy
import json
from typing import Any, Protocol

from pydantic import BaseModel

from repolens.ai.config import AiConfig
from repolens.ai.errors import (
    FILE_FALLBACK,
    FILE_TASK,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from repolens.ai.models import (
    CodeSummary,
    CodeSummaryContext,
    ProviderResult,
    ProviderUsage,
)
from repolens.ai.prompts import SYSTEM_INSTRUCTIONS, build_user_input


SCHEMA_NAME = "repolens_code_summary"

# JSON Schema keywords Structured Outputs may not accept in strict mode. The
# limits they express are enforced locally by `CodeSummary` instead.
_UNSUPPORTED_KEYWORDS = frozenset(
    {"title", "default", "minLength", "maxLength", "minItems", "maxItems", "minimum"}
)


class CodeSummaryProvider(Protocol):
    """Turns one file's context into a raw structured summary."""

    def summarize(
        self,
        context: CodeSummaryContext,
        repair_feedback: tuple[str, ...] = (),
    ) -> ProviderResult:
        """Return the model's answer for `context`.

        `repair_feedback` lists verification problems with a previous answer,
        for one bounded repair attempt.

        Raises:
          ProviderTimeoutError: The provider did not answer in time.
          ProviderUnavailableError: The provider failed or refused.
        """
        ...


def strict_output_schema(model: type[BaseModel] = CodeSummary) -> dict[str, Any]:
    """Return `model`'s JSON schema in the strict Structured Outputs form.

    Every object lists all of its properties as required and forbids others;
    keywords strict mode may reject are removed (their limits are re-checked
    locally when the answer is parsed).
    """
    schema = copy.deepcopy(model.model_json_schema(by_alias=True))
    _make_strict(schema)
    return schema


def _make_strict(node: Any) -> None:
    """Rewrite one schema node, and the schemas nested in it, in place."""
    if not isinstance(node, dict):
        return
    for keyword in _UNSUPPORTED_KEYWORDS & node.keys():
        del node[keyword]
    properties = node.get("properties")
    if isinstance(properties, dict):
        for value in properties.values():
            _make_strict(value)
        node["required"] = list(properties)
        node["additionalProperties"] = False
    for keyword in ("items", "additionalItems"):
        _make_strict(node.get(keyword))
    for keyword in ("anyOf", "allOf", "oneOf", "prefixItems"):
        for value in node.get(keyword, ()):
            _make_strict(value)
    for value in node.get("$defs", {}).values():
        _make_strict(value)


def build_request(
    config: AiConfig,
    context: CodeSummaryContext,
    repair_feedback: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return the keyword arguments for `client.responses.create`.

    Trusted instructions go in `instructions`; the file's metadata and source
    go only in `input`. `store=False` asks OpenAI not to keep the response.
    """
    request: dict[str, Any] = {
        "model": config.model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": build_user_input(context, repair_feedback),
        "text": {
            "format": {
                "type": "json_schema",
                "name": SCHEMA_NAME,
                "schema": strict_output_schema(),
                "strict": True,
            }
        },
        "max_output_tokens": config.max_output_tokens,
        "store": False,
    }
    if config.reasoning_effort:
        request["reasoning"] = {"effort": config.reasoning_effort}
    return request


def build_openai_client(config: AiConfig) -> Any:
    """Return an `openai.OpenAI` client for `config` (the key is never logged)."""
    from openai import OpenAI  # Imported lazily: only needed when enabled.

    return OpenAI(
        api_key=config.api_key,
        timeout=config.timeout_seconds,
        max_retries=config.max_retries,
    )


def call_structured(
    client: Any,
    config: AiConfig,
    request: dict[str, Any],
    *,
    task: str = FILE_TASK,
    noun: str = "summary",
    fallback: str = FILE_FALLBACK,
) -> ProviderResult:
    """Send one Structured Outputs request and return the parsed answer.

    `task` ("summarize this file"), `noun` ("summary") and `fallback` (what
    still works) only shape the error messages.

    Raises:
      ProviderTimeoutError: The provider did not answer in time.
      ProviderUnavailableError: The provider failed, refused, stopped early,
        or rate-limited the request.
    """
    import openai

    try:
        response = client.responses.create(**request, timeout=config.timeout_seconds)
    except openai.APITimeoutError as error:
        raise ProviderTimeoutError(task, fallback) from error
    except openai.RateLimitError as error:
        raise ProviderUnavailableError(
            "The AI provider is rate-limiting RepoLens right now.", fallback
        ) from error
    except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
        raise ProviderUnavailableError(
            "The AI provider rejected RepoLens's credentials.", fallback
        ) from error
    except openai.NotFoundError as error:
        raise ProviderUnavailableError(
            f"The AI provider does not offer the configured model '{config.model}'.",
            fallback,
        ) from error
    except openai.OpenAIError as error:
        raise ProviderUnavailableError(
            f"The AI provider could not {task}.", fallback
        ) from error

    return ProviderResult(
        payload=_parse_output(response, task=task, noun=noun, fallback=fallback),
        model=str(getattr(response, "model", None) or config.model),
        usage=_usage(response),
    )


class OpenAICodeSummaryProvider:
    """Summarize files with the OpenAI Responses API."""

    def __init__(self, config: AiConfig, client: Any | None = None) -> None:
        """Initialize the provider.

        Args:
          config: Model, limits, and the API key (used only to build the
            client; never logged).
          client: An `openai.OpenAI`-compatible client. Built from `config`
            when omitted; tests pass a fake.
        """
        self._config = config
        self._client = client if client is not None else build_openai_client(config)

    def summarize(
        self,
        context: CodeSummaryContext,
        repair_feedback: tuple[str, ...] = (),
    ) -> ProviderResult:
        return call_structured(
            self._client,
            self._config,
            build_request(self._config, context, repair_feedback),
        )


def _parse_output(
    response: Any,
    *,
    task: str = FILE_TASK,
    noun: str = "summary",
    fallback: str = FILE_FALLBACK,
) -> object:
    """Return the JSON answer, or a marker the validator will reject."""
    status = getattr(response, "status", None)
    if status == "incomplete":
        details = getattr(response, "incomplete_details", None)
        reason = getattr(details, "reason", None) or "unknown"
        raise ProviderUnavailableError(
            f"The AI provider stopped before finishing the {noun} ({reason}).", fallback
        )
    if status not in (None, "completed"):
        raise ProviderUnavailableError(f"The AI provider could not {task}.", fallback)
    for item in getattr(response, "output", None) or ():
        for part in getattr(item, "content", None) or ():
            if getattr(part, "type", None) == "refusal":
                raise ProviderUnavailableError(
                    f"The AI provider declined to {task}.", fallback
                )
    text = getattr(response, "output_text", "") or ""
    try:
        return json.loads(text)
    except ValueError:
        return {"_unparseable": True}


def _usage(response: Any) -> ProviderUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return ProviderUsage()
    return ProviderUsage(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )

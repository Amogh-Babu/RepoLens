"""AI file summaries: on-demand, verified, cached descriptions of analyzed files.

Optional and off by default. Deterministic parsing still owns all structure
(symbols, imports, the dependency graph, search); the model only writes the
natural-language summary, which is verified against that structure before it
is cached or shown. See `repolens.ai.service` for the request flow.
"""

from repolens.ai.config import DEFAULT_MODEL, AiConfig, AiConfigError, load_ai_config
from repolens.ai.endpoints import create_ai_router
from repolens.ai.models import CodeSummary, CodeSummaryContext
from repolens.ai.provider import CodeSummaryProvider, OpenAICodeSummaryProvider
from repolens.ai.service import CodeSummaryService

__all__ = [
    "DEFAULT_MODEL",
    "AiConfig",
    "AiConfigError",
    "CodeSummary",
    "CodeSummaryContext",
    "CodeSummaryProvider",
    "CodeSummaryService",
    "OpenAICodeSummaryProvider",
    "create_ai_router",
    "load_ai_config",
]

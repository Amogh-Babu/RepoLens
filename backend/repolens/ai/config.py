"""Configuration for AI file summaries, read from `REPOLENS_AI_*` variables.

AI summaries are off unless `REPOLENS_AI_ENABLED` is true and an
`OPENAI_API_KEY` is set. Every other value has a conservative default that
keeps one summary request small and bounded. The model identifier is only a
default: set `REPOLENS_AI_MODEL` to change it without touching code.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import os


DEFAULT_MODEL = "gpt-5.4-mini"

_TRUE = frozenset({"1", "true", "yes", "on"})


class AiConfigError(ValueError):
    """Raised when a `REPOLENS_AI_*` variable holds an unusable value."""


@dataclass(frozen=True)
class AiConfig:
    """Limits and switches for AI file summaries.

    Attributes:
      enabled: Whether AI summaries were switched on.
      api_key: The provider key. Never logged, serialized, or sent to the
        browser; `repr` hides it.
      model: Provider model identifier.
      timeout_seconds: Per-request provider timeout.
      max_input_chars: Most source characters sent in one request. A longer
        file is cut on function and class boundaries and marked partial.
      max_output_tokens: Cap on generated tokens per request.
      max_concurrent_requests: Model calls allowed at the same time.
      daily_call_limit: Model calls allowed per UTC day.
      max_retries: Provider retries on transient errors (rate limits, 5xx).
      regenerate_cooldown_seconds: Minimum gap between regenerations of one
        cached summary.
      reasoning_effort: Optional reasoning effort sent to reasoning models;
        empty sends none.
      input_cost_per_million: Optional USD price per million input tokens,
        used only to estimate cost in usage logs.
      output_cost_per_million: Optional USD price per million output tokens.
    """

    enabled: bool = False
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 30.0
    max_input_chars: int = 40_000
    max_output_tokens: int = 700
    max_concurrent_requests: int = 2
    daily_call_limit: int = 100
    max_retries: int = 1
    regenerate_cooldown_seconds: float = 60.0
    reasoning_effort: str = ""
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None

    def __repr__(self) -> str:
        key_state = "set" if self.api_key else "unset"
        return (
            f"AiConfig(enabled={self.enabled}, model={self.model!r}, "
            f"api_key=<{key_state}>)"
        )

    @property
    def active(self) -> bool:
        """Return whether summaries can be generated: enabled and keyed."""
        return self.enabled and bool(self.api_key)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "AiConfig":
        """Build the configuration from environment variables.

        Raises:
          AiConfigError: A numeric variable is not a valid positive number.
        """
        env = os.environ if environ is None else environ
        defaults = cls()
        return cls(
            enabled=env.get("REPOLENS_AI_ENABLED", "").strip().lower() in _TRUE,
            api_key=env.get("OPENAI_API_KEY", "").strip(),
            model=env.get("REPOLENS_AI_MODEL", "").strip() or defaults.model,
            timeout_seconds=_positive_float(
                env, "REPOLENS_AI_TIMEOUT_SECONDS", defaults.timeout_seconds
            ),
            max_input_chars=_positive_int(
                env, "REPOLENS_AI_MAX_INPUT_CHARS", defaults.max_input_chars
            ),
            max_output_tokens=_positive_int(
                env, "REPOLENS_AI_MAX_OUTPUT_TOKENS", defaults.max_output_tokens
            ),
            max_concurrent_requests=_positive_int(
                env,
                "REPOLENS_AI_MAX_CONCURRENT_REQUESTS",
                defaults.max_concurrent_requests,
            ),
            daily_call_limit=_positive_int(
                env, "REPOLENS_AI_DAILY_CALL_LIMIT", defaults.daily_call_limit
            ),
            max_retries=_non_negative_int(
                env, "REPOLENS_AI_MAX_RETRIES", defaults.max_retries
            ),
            regenerate_cooldown_seconds=_positive_float(
                env,
                "REPOLENS_AI_REGENERATE_COOLDOWN_SECONDS",
                defaults.regenerate_cooldown_seconds,
            ),
            reasoning_effort=env.get("REPOLENS_AI_REASONING_EFFORT", "").strip(),
            input_cost_per_million=_optional_price(
                env, "REPOLENS_AI_INPUT_COST_PER_MILLION"
            ),
            output_cost_per_million=_optional_price(
                env, "REPOLENS_AI_OUTPUT_COST_PER_MILLION"
            ),
        )


def _raw(env: Mapping[str, str], name: str) -> str:
    return env.get(name, "").strip()


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise AiConfigError(f"{name} must be a whole number, not {raw!r}.") from None
    if value <= 0:
        raise AiConfigError(f"{name} must be greater than zero.")
    return value


def _non_negative_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise AiConfigError(f"{name} must be a whole number, not {raw!r}.") from None
    if value < 0:
        raise AiConfigError(f"{name} must not be negative.")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = _raw(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise AiConfigError(f"{name} must be a number, not {raw!r}.") from None
    if value <= 0:
        raise AiConfigError(f"{name} must be greater than zero.")
    return value


def _optional_price(env: Mapping[str, str], name: str) -> float | None:
    raw = _raw(env, name)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise AiConfigError(f"{name} must be a number, not {raw!r}.") from None
    if value < 0:
        raise AiConfigError(f"{name} must not be negative.")
    return value

"""AI summary configuration: defaults, environment parsing, secrecy."""

import pytest

import logging

from repolens.ai import DEFAULT_MODEL, AiConfig, AiConfigError, load_ai_config


def test_defaults_keep_ai_off_and_bounded() -> None:
    config = AiConfig.from_environment({})

    assert config.enabled is False
    assert config.active is False
    assert config.model == DEFAULT_MODEL == "gpt-5.4-mini"
    assert config.timeout_seconds == 30
    assert config.max_input_chars == 40_000
    assert config.max_output_tokens == 4096
    assert config.max_concurrent_requests == 2
    assert config.daily_call_limit == 100
    assert config.client_hourly_limit == 10
    assert config.reasoning_effort == ""
    assert config.input_cost_per_million is None


def test_every_documented_variable_is_read() -> None:
    config = AiConfig.from_environment(
        {
            "REPOLENS_AI_ENABLED": "true",
            "OPENAI_API_KEY": " sk-test ",
            "REPOLENS_AI_MODEL": "some-other-model",
            "REPOLENS_AI_TIMEOUT_SECONDS": "12.5",
            "REPOLENS_AI_MAX_INPUT_CHARS": "1000",
            "REPOLENS_AI_MAX_OUTPUT_TOKENS": "300",
            "REPOLENS_AI_MAX_CONCURRENT_REQUESTS": "1",
            "REPOLENS_AI_DAILY_CALL_LIMIT": "5",
            "REPOLENS_AI_CLIENT_HOURLY_LIMIT": "3",
            "REPOLENS_AI_REASONING_EFFORT": "low",
            "REPOLENS_AI_INPUT_COST_PER_MILLION": "0.25",
            "REPOLENS_AI_OUTPUT_COST_PER_MILLION": "2",
        }
    )

    assert config.active
    assert config.api_key == "sk-test"
    assert config.model == "some-other-model"
    assert config.timeout_seconds == 12.5
    assert (config.max_input_chars, config.max_output_tokens) == (1000, 300)
    assert (config.max_concurrent_requests, config.daily_call_limit) == (1, 5)
    assert config.client_hourly_limit == 3
    assert config.reasoning_effort == "low"
    assert (config.input_cost_per_million, config.output_cost_per_million) == (0.25, 2.0)


def test_a_zero_client_hourly_limit_turns_the_per_visitor_limit_off() -> None:
    config = AiConfig.from_environment({"REPOLENS_AI_CLIENT_HOURLY_LIMIT": "0"})

    assert config.client_hourly_limit == 0


def test_enabled_without_a_key_is_not_active() -> None:
    config = AiConfig.from_environment({"REPOLENS_AI_ENABLED": "1"})

    assert config.enabled and not config.active


@pytest.mark.parametrize(
    "name, value",
    [
        ("REPOLENS_AI_TIMEOUT_SECONDS", "soon"),
        ("REPOLENS_AI_TIMEOUT_SECONDS", "0"),
        ("REPOLENS_AI_MAX_INPUT_CHARS", "-1"),
        ("REPOLENS_AI_DAILY_CALL_LIMIT", "1.5"),
        ("REPOLENS_AI_INPUT_COST_PER_MILLION", "-0.1"),
        ("REPOLENS_AI_TIMEOUT_SECONDS", "inf"),
        ("REPOLENS_AI_REGENERATE_COOLDOWN_SECONDS", "nan"),
        ("REPOLENS_AI_REGENERATE_COOLDOWN_SECONDS", "-inf"),
        ("REPOLENS_AI_INPUT_COST_PER_MILLION", "nan"),
        ("REPOLENS_AI_OUTPUT_COST_PER_MILLION", "Infinity"),
    ],
)
def test_invalid_numbers_are_rejected(name: str, value: str) -> None:
    with pytest.raises(AiConfigError, match=name):
        AiConfig.from_environment({name: value})


def test_the_key_never_appears_in_repr() -> None:
    config = AiConfig(enabled=True, api_key="sk-very-secret")

    assert "sk-very-secret" not in repr(config)
    assert "api_key=<set>" in repr(config)


def test_an_invalid_setting_disables_ai_instead_of_stopping_the_server(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    config = load_ai_config(
        {
            "REPOLENS_AI_ENABLED": "true",
            "OPENAI_API_KEY": "sk-should-not-be-logged",
            "REPOLENS_AI_DAILY_CALL_LIMIT": "lots",
        }
    )

    assert config.active is False
    assert "REPOLENS_AI_DAILY_CALL_LIMIT" in caplog.text
    assert "sk-should-not-be-logged" not in caplog.text


def test_a_non_finite_setting_disables_ai() -> None:
    config = load_ai_config(
        {
            "REPOLENS_AI_ENABLED": "true",
            "OPENAI_API_KEY": "sk-test",
            "REPOLENS_AI_REGENERATE_COOLDOWN_SECONDS": "nan",
        }
    )

    assert config.active is False

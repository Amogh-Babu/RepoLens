"""Structured errors for AI file summaries, in the API's `{code, message, hint}` shape.

Every failure here is specific to one summary request: none of them fails or
changes the analysis, and the graph, search, overview, and deterministic
descriptions keep working.
"""


class SummaryError(Exception):
    """Base error for a summary request that could not be completed."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        status_code: int = 502,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code
        # Sent as the HTTP `Retry-After` header when set.
        self.retry_after_seconds = retry_after_seconds

    def to_dict(self) -> dict[str, str | None]:
        """Serialize the error into the standard {code, message, hint} shape."""
        return {"code": self.code, "message": self.message, "hint": self.hint}


class AiDisabledError(SummaryError):
    """AI summaries are switched off or have no provider key configured."""

    def __init__(self) -> None:
        super().__init__(
            code="AI_DISABLED",
            message="AI file summaries are not enabled on this server.",
            hint=(
                "The rest of RepoLens works without them. To enable them, set "
                "REPOLENS_AI_ENABLED=true and OPENAI_API_KEY on the backend."
            ),
            status_code=503,
        )


class SourceRejectedError(SummaryError):
    """The file cannot be summarized: unsafe path, too large, binary, or not text."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="SOURCE_UNSUPPORTED",
            message=message,
            hint="AI summaries cover UTF-8 Python files that were analyzed.",
            status_code=422,
        )


class SourceFetchError(SummaryError):
    """The file's source could not be downloaded from GitHub."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "SOURCE_UNAVAILABLE",
        status_code: int = 502,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            hint="Try again in a moment. The rest of the analysis is unaffected.",
            status_code=status_code,
        )


class SourceMismatchError(SummaryError):
    """The downloaded source does not match what the analysis recorded."""

    def __init__(self) -> None:
        super().__init__(
            code="SOURCE_MISMATCH",
            message=(
                "The file downloaded from GitHub does not match the analyzed "
                "commit, so it was not summarized."
            ),
            hint="Re-analyze the repository and try again.",
            status_code=409,
        )


class SummaryBusyError(SummaryError):
    """Every model call slot is in use."""

    def __init__(self) -> None:
        super().__init__(
            code="AI_BUSY",
            message="RepoLens is generating other summaries right now.",
            hint="Try again in a few seconds.",
            status_code=429,
        )


class DailyLimitError(SummaryError):
    """Today's model-call budget is spent."""

    def __init__(self) -> None:
        super().__init__(
            code="AI_DAILY_LIMIT",
            message="Today's AI summary budget has been used up.",
            hint="Cached summaries are still available. New ones resume tomorrow (UTC).",
            status_code=429,
        )


class ClientLimitError(SummaryError):
    """This visitor generated its hourly share of new summaries."""

    def __init__(self, limit: int, retry_after_seconds: int) -> None:
        minutes = max(1, -(-retry_after_seconds // 60))
        wait = "about a minute" if minutes == 1 else f"about {minutes} minutes"
        noun = "summary" if limit == 1 else "summaries"
        super().__init__(
            code="AI_CLIENT_LIMIT",
            message=f"You have generated {limit} new AI {noun} in the last hour.",
            hint=(
                f"Cached summaries are still available. You can generate more in {wait}."
            ),
            status_code=429,
            retry_after_seconds=retry_after_seconds,
        )


class RegenerateCooldownError(SummaryError):
    """A summary was regenerated too recently."""

    def __init__(self, seconds_left: int) -> None:
        super().__init__(
            code="AI_REGENERATE_COOLDOWN",
            message="This summary was generated moments ago.",
            hint=f"Wait {seconds_left} seconds before regenerating it.",
            status_code=429,
        )


FILE_TASK = "summarize this file"
FILE_FALLBACK = "The file's symbols, imports, and map still work."


class ProviderTimeoutError(SummaryError):
    """The model provider did not answer in time."""

    def __init__(self, task: str = FILE_TASK, fallback: str = FILE_FALLBACK) -> None:
        super().__init__(
            code="AI_TIMEOUT",
            message=f"The AI provider took too long to {task}.",
            hint=f"Try again. {fallback}",
            status_code=504,
        )


class ProviderUnavailableError(SummaryError):
    """The model provider failed, refused, or rate-limited the request."""

    def __init__(
        self,
        message: str = f"The AI provider could not {FILE_TASK}.",
        fallback: str = FILE_FALLBACK,
    ) -> None:
        super().__init__(
            code="AI_UNAVAILABLE",
            message=message,
            hint=f"Try again later. {fallback}",
            status_code=502,
        )


class SummaryValidationError(SummaryError):
    """The model's answer failed verification, even after one repair attempt."""

    def __init__(
        self,
        problems: tuple[str, ...],
        *,
        message: str = (
            "The AI summary could not be verified against the source, so "
            "it is not shown."
        ),
        hint: str = "The static description of this file is still available. Try again later.",
    ) -> None:
        super().__init__(
            code="AI_SUMMARY_UNVERIFIED",
            message=message,
            hint=hint,
            status_code=502,
        )
        self.problems = problems


class SearchOverviewValidationError(SummaryValidationError):
    """A search overview failed verification, even after one repair attempt."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(
            problems,
            message=(
                "The AI overview named files or code that are not in these search "
                "results, so it is not shown."
            ),
            hint="The reading list below is unaffected. Try again later.",
        )

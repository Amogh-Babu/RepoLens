"""Verify a model's search overview against the search results it was given.

The checks are structural, like those for file summaries
(`repolens.ai.validation`): every path the overview recommends must be one of
the results sent, and every backticked code name must be a listed path or
symbol (or a word from one), or Python's own vocabulary. They reject invented
files and invented functions. They cannot prove the prose is right, which is
why the frontend labels the overview as AI-generated and every recommended
path opens the file itself.
"""

from pydantic import ValidationError

from repolens.ai.search_models import SearchOverview, SearchOverviewContext
from repolens.ai.validation import BACKTICKED, IDENTIFIER, PYTHON_WORDS


_MAX_PROBLEMS = 12


class SearchValidationResult:
    """The outcome of validating one overview; `overview` is set only when ok."""

    def __init__(self, overview: SearchOverview | None, problems: tuple[str, ...]) -> None:
        self.overview = overview
        self.problems = problems

    @property
    def ok(self) -> bool:
        return self.overview is not None and not self.problems


def validate_search_overview(
    payload: object, context: SearchOverviewContext
) -> SearchValidationResult:
    """Parse `payload` as a `SearchOverview` and check it against `context`.

    Problems are short, deterministic descriptions suitable for the repair
    prompt and for logs; they never include repository text beyond a path or
    name the model itself wrote.
    """
    try:
        overview = SearchOverview.model_validate(payload)
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(part) for part in item.get('loc', ())) or 'answer'}: "
            f"{item.get('msg', 'invalid value')}."
            for item in error.errors()[:_MAX_PROBLEMS]
        ]
        return SearchValidationResult(
            None, tuple(problems) or ("The answer did not match the required schema.",)
        )

    problems: list[str] = []
    problems.extend(_check_paths(overview, context))
    problems.extend(_check_code_names(overview, context))
    if problems:
        return SearchValidationResult(None, tuple(problems[:_MAX_PROBLEMS]))
    return SearchValidationResult(overview, ())


def _check_paths(overview: SearchOverview, context: SearchOverviewContext) -> list[str]:
    allowed = set(context.paths)
    problems = []
    if overview.start_here.path not in allowed:
        problems.append(
            f"startHere '{overview.start_here.path}' is not one of the listed results."
        )
    seen = {overview.start_here.path}
    for step in overview.read_next:
        if step.path not in allowed:
            problems.append(f"readNext '{step.path}' is not one of the listed results.")
        elif step.path in seen:
            problems.append(f"readNext lists '{step.path}' more than once or repeats startHere.")
        seen.add(step.path)
    return problems


def _check_code_names(overview: SearchOverview, context: SearchOverviewContext) -> list[str]:
    """Reject backticked names that appear nowhere in the results sent."""
    known = set(context.paths)
    for item in context.files:
        known.update(item.symbols)
    words = set(PYTHON_WORDS)
    for name in known:
        words.update(IDENTIFIER.findall(name))
    for item in context.files:
        # Names quoted in a docstring or a cached summary were shown to the model.
        for text in (item.docstring, item.ai_summary or ""):
            words.update(IDENTIFIER.findall(text))

    problems = []
    reported: set[str] = set()
    for text in _prose(overview):
        for match in BACKTICKED.finditer(text):
            name = match.group(1).strip()
            if name in known or name in reported:
                continue
            missing = [word for word in IDENTIFIER.findall(name) if word not in words]
            if missing:
                reported.add(name)
                problems.append(
                    f"The overview mentions `{name}`, but '{missing[0]}' is not a listed "
                    "path or symbol of these results."
                )
    return problems


def _prose(overview: SearchOverview) -> list[str]:
    return [
        overview.summary,
        overview.start_here.reason,
        *(step.reason for step in overview.read_next),
        *overview.uncertainties,
    ]

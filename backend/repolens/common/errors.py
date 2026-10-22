"""The shared error model.

Every expected failure is raised as a RepolensError so the API layer can turn
it into the single {code, message, hint} response shape.
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Machine-readable error codes. Add new codes through a GitHub issue."""

    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_HOST = "UNSUPPORTED_HOST"
    REPO_NOT_FOUND = "REPO_NOT_FOUND"
    NO_PYTHON_FILES = "NO_PYTHON_FILES"
    REPO_TOO_LARGE = "REPO_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"


class RepolensError(Exception):
    """An expected failure with a user-facing explanation.

    Attributes:
        code: Machine-readable error code.
        message: What went wrong.
        hint: What the user can do next.
    """

    def __init__(self, code: ErrorCode, message: str, hint: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, str]:
        """Returns the {code, message, hint} shape sent to the client."""
        return {
            "code": self.code.value,
            "message": self.message,
            "hint": self.hint,
        }

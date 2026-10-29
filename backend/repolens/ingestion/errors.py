"""Structured errors raised by RepoLens repository ingestion.

Every error carries the pitch's ``{code, message, hint}`` shape so the API
layer can serialize it without translating exception types.
"""


class IngestionError(Exception):
    """Base error raised by ingestion with structured API fields."""

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code

    def to_dict(self) -> dict[str, str | None]:
        """Serialize the error into the standard {code, message, hint} shape."""
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


class InvalidRepoUrlError(IngestionError):
    """Raised when a repository URL is malformed, unsafe, or not a repo root."""

    def __init__(
        self,
        message: str = "This is not a valid repository URL.",
        hint: str = "Use the format https://github.com/<owner>/<repo>.",
        code: str = "INVALID_URL",
    ) -> None:
        super().__init__(code=code, message=message, hint=hint, status_code=400)


class UnsupportedHostError(InvalidRepoUrlError):
    """Raised when a URL points at a Git host RepoLens does not support.

    Subclasses ``InvalidRepoUrlError`` so callers that only need to know the URL
    was rejected can catch a single type, while callers that report the reason
    can still distinguish the ``UNSUPPORTED_HOST`` code.
    """

    def __init__(self, host: str) -> None:
        super().__init__(
            code="UNSUPPORTED_HOST",
            message=f"Only GitHub repositories are supported, not '{host}'.",
            hint=(
                "Use a public GitHub repository URL: "
                "https://github.com/<owner>/<repo>."
            ),
        )


class InvalidCommitShaError(IngestionError):
    """Raised when a commit SHA is not a full 40-character hexadecimal SHA."""

    def __init__(self, raw_sha: str) -> None:
        super().__init__(
            code="INVALID_SHA",
            message="A full 40-character commit SHA is required.",
            hint=(
                "Resolve branches and tags to a commit SHA before downloading, "
                "so the snapshot is reproducible."
            ),
            status_code=400,
        )
        self.raw_sha = raw_sha


class RepoNotFoundError(IngestionError):
    """Raised when GitHub has no public repository at the given URL."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            code="REPO_NOT_FOUND",
            message=f"Could not find a public repository at github.com/{slug}.",
            hint="Check the URL. Private repositories are not supported.",
            status_code=404,
        )


class RepoEmptyError(IngestionError):
    """Raised when a repository has no commits or no files to analyze."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            code="REPO_EMPTY",
            message=f"The repository github.com/{slug} is empty.",
            hint="Analyze a repository that has at least one commit.",
            status_code=422,
        )


class NoPythonFilesError(IngestionError):
    """Raised when a snapshot contains no files RepoLens can analyze."""

    def __init__(self) -> None:
        super().__init__(
            code="NO_PYTHON_FILES",
            message="This repository has no Python files to analyze.",
            hint="RepoLens currently supports Python repositories only.",
            status_code=422,
        )


class RefNotFoundError(IngestionError):
    """Raised when a branch, tag, or commit does not exist in the repository."""

    def __init__(self, ref: str) -> None:
        super().__init__(
            code="REF_NOT_FOUND",
            message=f"The branch, tag, or commit '{ref}' does not exist.",
            hint="Leave the ref empty to use the default branch.",
            status_code=404,
        )


class RateLimitedError(IngestionError):
    """Raised when GitHub refuses a request because of its rate limit."""

    def __init__(self) -> None:
        super().__init__(
            code="RATE_LIMITED",
            message="GitHub is rate-limiting RepoLens right now.",
            hint="Wait a few minutes and try again.",
            status_code=429,
        )


class GitHubUnavailableError(IngestionError):
    """Raised when GitHub cannot be reached or answers with a server error."""

    def __init__(self, message: str = "GitHub could not be reached.") -> None:
        super().__init__(
            code="GITHUB_UNAVAILABLE",
            message=message,
            hint="Wait a moment and try again.",
            status_code=502,
        )


class ArchiveDownloadError(IngestionError):
    """Raised when the archive cannot be downloaded from the Git host."""

    def __init__(
        self,
        message: str,
        hint: str = "Check the repository URL and commit SHA, then try again.",
        status_code: int = 502,
    ) -> None:
        super().__init__(
            code="DOWNLOAD_FAILED",
            message=message,
            hint=hint,
            status_code=status_code,
        )


class ArchiveTooLargeError(IngestionError):
    """Raised when an archive exceeds the configured download or size cap."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="ARCHIVE_TOO_LARGE",
            message=message,
            hint="Analyze a smaller repository.",
            status_code=413,
        )


class ArchiveFormatError(IngestionError):
    """Raised when the downloaded bytes are not a readable, non-empty archive."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="INVALID_ARCHIVE",
            message=message,
            hint="Re-run the analysis; the download may have been truncated.",
            status_code=502,
        )


class UnsafeArchiveError(IngestionError):
    """Raised when an archive member would write outside the snapshot directory.

    Covers path traversal ("zip slip"), absolute paths, and entries that are not
    plain files or directories, such as symlinks and device nodes.
    """

    def __init__(self, member_name: str, reason: str) -> None:
        super().__init__(
            code="UNSAFE_ARCHIVE",
            message=f"Refused unsafe archive entry '{member_name}': {reason}.",
            hint="This repository archive cannot be extracted safely.",
            status_code=422,
        )
        self.member_name = member_name
        self.reason = reason


class DestinationNotEmptyError(IngestionError):
    """Raised when a snapshot would be extracted over existing files."""

    def __init__(self, destination: str) -> None:
        super().__init__(
            code="DESTINATION_NOT_EMPTY",
            message=f"Snapshot directory '{destination}' is not empty.",
            hint="Extract each snapshot into a fresh directory.",
            status_code=500,
        )

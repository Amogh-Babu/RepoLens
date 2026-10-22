from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    """A filtered copy of one repository at one commit, stored on disk.

    Attributes:
        owner: GitHub owner, as normalized by ingestion.
        repo: Repository name, as normalized by ingestion.
        sha: Full 40-character commit SHA the files came from.
        root: Temporary directory holding the extracted files. The caller
            deletes it when analysis finishes, on success or on error.
        files: Repo-relative POSIX paths of the files kept after filtering.
        excluded_count: Number of files removed by filtering, for the summary.
    """

    owner: str
    repo: str
    sha: str
    root: Path
    files: tuple[str, ...]
    excluded_count: int = 0

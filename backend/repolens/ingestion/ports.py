from typing import Protocol

from repolens.ingestion.models import Snapshot


class RepoSource(Protocol):
    """Fetches a repository snapshot from a Git host."""

    def fetch(self, owner: str, repo: str, ref: str | None = None) -> Snapshot:
        """Downloads one repository at one commit without running its code.

        Args:
            owner: Repository owner.
            repo: Repository name.
            ref: Branch, tag or commit SHA. None means the default branch.

        Returns:
            A Snapshot whose sha is the resolved full commit SHA.

        Raises:
            RepolensError: If the repository is missing, private, too large,
                rate limited or cannot be downloaded.
        """

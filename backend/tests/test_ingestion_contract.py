import dataclasses
import unittest
from pathlib import Path

from repolens.common import ErrorCode, RepolensError
from repolens.ingestion import Snapshot


class RepolensErrorTest(unittest.TestCase):
    def test_to_dict_has_code_message_and_hint(self) -> None:
        error = RepolensError(
            ErrorCode.INVALID_URL,
            "That is not a valid repository URL.",
            "Use https://github.com/<owner>/<repo>.",
        )

        self.assertEqual(
            error.to_dict(),
            {
                "code": "INVALID_URL",
                "message": "That is not a valid repository URL.",
                "hint": "Use https://github.com/<owner>/<repo>.",
            },
        )

    def test_can_be_raised_and_caught_with_its_message(self) -> None:
        with self.assertRaises(RepolensError) as context:
            raise RepolensError(ErrorCode.RATE_LIMITED, "Slow down.", "Retry later.")

        self.assertEqual(str(context.exception), "Slow down.")
        self.assertEqual(context.exception.code, ErrorCode.RATE_LIMITED)


class SnapshotTest(unittest.TestCase):
    def test_defaults_and_immutability(self) -> None:
        snapshot = Snapshot(
            owner="octocat",
            repo="hello",
            sha="a" * 40,
            root=Path("/tmp/snap"),
            files=("pkg/main.py",),
        )

        self.assertEqual(snapshot.excluded_count, 0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.sha = "b" * 40  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

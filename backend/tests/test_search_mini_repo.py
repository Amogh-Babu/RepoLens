import json
import unittest

from repolens.search import SearchService

from search_fixture import FIXTURE_ROOT, MiniRepoSearchIndex


class SearchMiniRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = MiniRepoSearchIndex()
        self.service = SearchService(self.index)

    def test_fixture_index_covers_every_python_file(self) -> None:
        indexed_paths = {document.path for document in self.index.documents}
        source_paths = {
            path.relative_to(FIXTURE_ROOT).as_posix()
            for path in (FIXTURE_ROOT / "app").rglob("*.py")
        }

        self.assertEqual(source_paths, indexed_paths)

    def test_expected_feature_queries_return_reading_orders(self) -> None:
        cases = json.loads((FIXTURE_ROOT / "search_cases.json").read_text(encoding="utf-8"))

        for case in cases:
            with self.subTest(query=case["query"]):
                page = self.service.search(self.index.analysis_id, case["query"])
                self.assertEqual(
                    case["expected_paths"],
                    [result.path for result in page.results],
                )

    def test_reading_order_places_matched_dependencies_before_callers(self) -> None:
        page = self.service.search(self.index.analysis_id, "authentication")
        ordered_paths = [result.path for result in page.results]

        self.assertLess(
            ordered_paths.index("app/authentication/service.py"),
            ordered_paths.index("app/authentication/routes.py"),
        )
        repository_result = next(
            result for result in page.results if result.path == "app/users/repository.py"
        )
        self.assertIn("depended on by 2 other matching file(s)", repository_result.reason)


if __name__ == "__main__":
    unittest.main()
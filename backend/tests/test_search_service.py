import unittest

from repolens.search import (
    PaginationValidationError,
    QueryValidationError,
    SearchDocument,
    SearchService,
)


class InMemorySearchIndex:
    def __init__(self, documents_by_analysis: dict[str, list[SearchDocument]]) -> None:
        self._documents_by_analysis = documents_by_analysis

    def get_search_documents(self, analysis_id: str) -> list[SearchDocument]:
        return self._documents_by_analysis.get(analysis_id, [])


class SearchServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = [
            SearchDocument(
                path="src/authentication.py",
                symbols=("login_user",),
                references=("users.models",),
                comments=("Validate authentication credentials",),
            )
        ]
        self.index = InMemorySearchIndex({"analysis-1": self.documents})
        self.service = SearchService(self.index)

    def test_matches_names_symbols_references_and_comments(self) -> None:
        page = self.service.search("analysis-1", "authentication login users")

        self.assertEqual(["src/authentication.py"], [result.path for result in page.results])
        self.assertEqual(
            {"filename", "symbol", "reference", "comment"},
            {match.kind for match in page.results[0].matches},
        )
        self.assertIn("authentication.py", page.results[0].reason)

    def test_ranks_shared_dependencies_earlier_and_explains_them(self) -> None:
        documents = [
            SearchDocument(path="auth/core.py", symbols=("authenticate",)),
            SearchDocument(
                path="auth/routes.py",
                symbols=("authenticate_request",),
                depended_on_by=("auth/tests.py",),
            ),
            SearchDocument(path="auth/tests.py", comments=("authenticate user",)),
        ]
        service = SearchService(InMemorySearchIndex({"analysis-1": documents}))

        page = service.search("analysis-1", "authenticate")

        self.assertEqual("auth/routes.py", page.results[0].path)
        self.assertIn("depended on by 1 other matching file", page.results[0].reason)
        self.assertEqual(
            list(page.results),
            sorted(page.results, key=lambda result: (-result.score, result.path.casefold())),
        )

    def test_ties_are_sorted_by_path(self) -> None:
        documents = [
            SearchDocument(path="zeta/auth.py"),
            SearchDocument(path="alpha/auth.py"),
        ]
        service = SearchService(InMemorySearchIndex({"analysis-1": documents}))

        page = service.search("analysis-1", "auth")

        self.assertEqual(["alpha/auth.py", "zeta/auth.py"], [result.path for result in page.results])

    def test_dependency_cycles_have_deterministic_order(self) -> None:
        documents = [
            SearchDocument(path="alpha/cycle.py", depended_on_by=("zeta/cycle.py",)),
            SearchDocument(path="zeta/cycle.py", depended_on_by=("alpha/cycle.py",)),
        ]
        service = SearchService(InMemorySearchIndex({"analysis-1": documents}))

        first_result = service.search("analysis-1", "cycle")
        second_result = service.search("analysis-1", "cycle")

        expected_paths = ["alpha/cycle.py", "zeta/cycle.py"]
        self.assertEqual(expected_paths, [result.path for result in first_result.results])
        self.assertEqual(first_result, second_result)

    def test_rejects_empty_and_overlong_queries(self) -> None:
        for query in ("  \n", "x" * 201):
            with self.subTest(query_length=len(query)):
                with self.assertRaises(QueryValidationError):
                    self.service.search("analysis-1", query)

    def test_no_matches_returns_empty_list(self) -> None:
        page = self.service.search("analysis-1", "database")

        self.assertEqual((), page.results)
        self.assertEqual(0, page.total)
        self.assertFalse(page.has_more)

    def test_searches_only_the_requested_analysis_and_paginates(self) -> None:
        documents = [SearchDocument(path=f"src/auth_{index}.py") for index in range(3)]
        index = InMemorySearchIndex({"analysis-1": documents, "analysis-2": []})
        service = SearchService(index)

        first_page = service.search("analysis-1", "auth", limit=2)
        second_page = service.search("analysis-1", "auth", offset=2, limit=2)
        other_analysis = service.search("analysis-2", "auth")

        self.assertEqual(3, first_page.total)
        self.assertTrue(first_page.has_more)
        self.assertEqual(1, len(second_page.results))
        self.assertFalse(second_page.has_more)
        self.assertEqual((), other_analysis.results)

    def test_rejects_invalid_pagination(self) -> None:
        for offset, limit in ((-1, 20), (0, 0), (0, 101)):
            with self.subTest(offset=offset, limit=limit):
                with self.assertRaises(PaginationValidationError):
                    self.service.search("analysis-1", "auth", offset=offset, limit=limit)

    def test_reasons_are_single_line_and_bound_evidence_length(self) -> None:
        long_comment = "authentication " + "context " * 30
        service = SearchService(
            InMemorySearchIndex(
                {"analysis-1": [SearchDocument(path="src/auth.py", comments=(long_comment,))]}
            )
        )

        page = service.search("analysis-1", "authentication")

        self.assertNotIn("\n", page.results[0].reason)
        self.assertIn("...", page.results[0].reason)


if __name__ == "__main__":
    unittest.main()
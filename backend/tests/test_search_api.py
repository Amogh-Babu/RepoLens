import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from repolens.api.search import install_search_api
from repolens.search import SearchService

from search_fixture import MiniRepoSearchIndex


class SearchApiTest(unittest.TestCase):
    def setUp(self) -> None:
        index = MiniRepoSearchIndex()
        app = FastAPI()
        install_search_api(app, SearchService(index))
        self.client = TestClient(app)
        self.analysis_id = index.analysis_id

    def test_search_endpoint_returns_ranked_page_and_evidence(self) -> None:
        response = self.client.get(
            f"/analyses/{self.analysis_id}/search",
            params={"q": "authentication", "limit": 2},
        )

        self.assertEqual(200, response.status_code)
        result = response.json()
        self.assertEqual(4, result["total"])
        self.assertTrue(result["has_more"])
        self.assertEqual(2, len(result["results"]))
        self.assertTrue(result["results"][0]["reason"])
        self.assertTrue(result["results"][0]["matches"])

    def test_empty_query_returns_structured_error(self) -> None:
        response = self.client.get(
            f"/analyses/{self.analysis_id}/search", params={"q": "   "}
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual(
            {"code", "message", "hint"},
            set(response.json()),
        )

    def test_missing_query_returns_structured_error(self) -> None:
        response = self.client.get(f"/analyses/{self.analysis_id}/search")

        self.assertEqual(422, response.status_code)
        self.assertEqual("INVALID_REQUEST", response.json()["code"])

    def test_missing_analysis_returns_reanalysis_hint(self) -> None:
        response = self.client.get("/analyses/expired/search", params={"q": "login"})

        self.assertEqual(404, response.status_code)
        self.assertEqual("ANALYSIS_UNAVAILABLE", response.json()["code"])
        self.assertIn("Re-analyze", response.json()["hint"])

    def test_invalid_page_size_uses_structured_error(self) -> None:
        response = self.client.get(
            f"/analyses/{self.analysis_id}/search",
            params={"q": "login", "limit": 101},
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual("INVALID_REQUEST", response.json()["code"])

    def test_search_validation_does_not_override_other_api_routes(self) -> None:
        app = FastAPI()

        @app.get("/other")
        def other_route(value: int) -> dict[str, int]:
            return {"value": value}

        index = MiniRepoSearchIndex()
        install_search_api(app, SearchService(index))
        response = TestClient(app).get("/other", params={"value": "invalid"})

        self.assertEqual(422, response.status_code)
        self.assertIn("detail", response.json())
        self.assertNotIn("code", response.json())


if __name__ == "__main__":
    unittest.main()
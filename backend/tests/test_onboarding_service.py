from repolens.graph.models import DependencyGraph, GraphEdge, GraphNode, ModuleGroup
from repolens.onboarding.service import build_overview
from repolens.search.models import SearchDocument


def test_build_overview_suggests_entry_points_core_files_and_tour() -> None:
    graph = DependencyGraph(
        analysis_id="analysis-test",
        repo="https://github.com/example/project",
        sha="a" * 40,
        modules=(
            ModuleGroup("app", "app", ("app/main.py", "app/service.py")),
            ModuleGroup("app/core", "core", ("app/core/config.py",)),
            ModuleGroup("tests", "tests", ("tests/test_service.py",)),
        ),
        files=(
            GraphNode("app/main.py", "app", True, 30),
            GraphNode("app/service.py", "app", True, 60),
            GraphNode("app/core/config.py", "app/core", True, 20),
            GraphNode("tests/test_service.py", "tests", True, 25),
        ),
        edges=(
            GraphEdge("app/main.py", "app/service.py"),
            GraphEdge("app/service.py", "app/core/config.py"),
            GraphEdge("tests/test_service.py", "app/service.py"),
        ),
    )
    documents = [
        SearchDocument(path="app/main.py", docstrings=("Start the service.",)),
        SearchDocument(path="app/service.py", symbols=("serve",)),
        SearchDocument(path="app/core/config.py", symbols=("Settings",)),
    ]

    overview = build_overview(graph, documents)

    assert overview["entryPoints"][0]["path"] == "app/main.py"
    assert overview["coreFiles"][0]["path"] == "app/core/config.py"
    tour_paths = [step["path"] for step in overview["tour"]]
    assert tour_paths.index("app/core/config.py") < tour_paths.index("app/main.py")
    assert {item["category"] for item in overview["categories"]} == {
        "source",
        "test",
    }
    assert overview["architecture"]["edges"] == [
        {"source": "app", "target": "app/core", "count": 1}
    ]
    assert overview["areas"]
    assert overview["entryPoints"][0]["summary"] == "Start the service."


def test_build_overview_handles_an_empty_graph() -> None:
    graph = DependencyGraph("analysis-empty", "repo", "sha", (), (), ())

    overview = build_overview(graph, [])

    assert overview == {
        "entryPoints": [],
        "coreFiles": [],
        "architecture": {
            "packages": [],
            "edges": [],
            "layers": [],
            "hasCycles": False,
        },
        "areas": [],
        "tour": [],
        "categories": [],
    }
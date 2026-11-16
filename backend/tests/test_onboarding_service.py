from repolens.analysis.python_analyzer import PythonAnalyzer
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


def test_detects_code_based_entry_points_beyond_filenames() -> None:
    analyzer = PythonAnalyzer()
    factory_parsed = analyzer.analyze(
        "pkg/bootstrap.py",
        "from fastapi import FastAPI\n\ndef create_app() -> FastAPI:\n    return FastAPI()\n",
    )
    script_parsed = analyzer.analyze(
        "pkg/runner.py",
        "def run_job() -> None:\n    pass\n\nif __name__ == '__main__':\n    run_job()\n",
    )
    cli_parsed = analyzer.analyze(
        "pkg/commands.py",
        "import click\n\n@click.command()\ndef sync() -> None:\n    pass\n",
    )
    assert "app_factory" in factory_parsed.entry_markers
    assert "main_guard" in script_parsed.entry_markers
    assert "cli_decorator" in cli_parsed.entry_markers

    graph = DependencyGraph(
        analysis_id="analysis-code-entries",
        repo="https://github.com/example/project",
        sha="b" * 40,
        modules=(
            ModuleGroup(
                "pkg",
                "pkg",
                ("pkg/bootstrap.py", "pkg/runner.py", "pkg/commands.py", "pkg/models.py"),
            ),
        ),
        files=(
            GraphNode("pkg/bootstrap.py", "pkg", True, 4),
            GraphNode("pkg/runner.py", "pkg", True, 5),
            GraphNode("pkg/commands.py", "pkg", True, 5),
            GraphNode("pkg/models.py", "pkg", True, 10),
        ),
        edges=(),
    )
    documents = [
        SearchDocument(
            path="pkg/bootstrap.py",
            symbols=("create_app",),
            references=("fastapi",),
            entry_markers=factory_parsed.entry_markers,
        ),
        SearchDocument(
            path="pkg/runner.py",
            symbols=("run_job",),
            entry_markers=script_parsed.entry_markers,
        ),
        SearchDocument(
            path="pkg/commands.py",
            symbols=("sync",),
            references=("click",),
            entry_markers=cli_parsed.entry_markers,
        ),
        SearchDocument(
            path="pkg/models.py",
            symbols=("User",),
        ),
    ]

    overview = build_overview(graph, documents)
    by_path = {item["path"]: item["reason"] for item in overview["entryPoints"]}
    assert set(by_path) == {"pkg/bootstrap.py", "pkg/runner.py", "pkg/commands.py"}
    assert "factory" in by_path["pkg/bootstrap.py"]
    assert "__main__" in by_path["pkg/runner.py"]
    assert "command-line" in by_path["pkg/commands.py"]
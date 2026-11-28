"""Evaluate search on separately checked-out repositories with public reading guides."""

import argparse
from pathlib import Path

from benchmarks.search_precision import build_search_service, repolens_top_paths
from repolens.search.embedding import FastEmbedEmbedder


# The listed paths are guide-backed starting points, not exhaustive relevance
# judgments. Negative queries are intended to have no match in that checkout.
CASES = {
    "issue": (
        ("elbow", ()),
        ("concertina", ()),
        ("datastore", ()),
        ("marine biology", ()),
        ("concert ticket sales", ()),
        ("virtual machine hardware", ("py-vmhardware.py",)),
        ("vm disk details", ("py-vmhardware.py",)),
        ("snapshot report", ("py-snaplist.py",)),
        ("retrieve virtual machine properties", ("get_vm_properties.py",)),
    ),
    "flask": (
        ("Flask request dispatch", ("src/flask/app.py",)),
        ("before request callback", ("src/flask/app.py", "src/flask/sansio/scaffold.py")),
        ("starting a web server", ("src/flask/app.py", "src/flask/cli.py")),
        ("elbow concertina", ()),
        ("marine biology", ()),
        ("concert ticket sales", ()),
    ),
    "natsume": (
        ("corpus normalization and pattern extraction", ("src/natsume_simple/pattern_extraction.py",)),
        ("artifact validation and selection", ("src/natsume_simple/artifact_registry.py",)),
        ("public API service", ("src/natsume_simple/api.py",)),
        ("validate stored corpus before serving", ("src/natsume_simple/artifact_registry.py",)),
        ("elbow concertina", ()),
        ("marine biology", ()),
        ("concert ticket sales", ()),
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in CASES:
        parser.add_argument(f"--{name}", type=Path, required=True, help=f"{name} checkout")
    args = parser.parse_args()
    embedder = FastEmbedEmbedder()
    for name, queries in CASES.items():
        root = getattr(args, name)
        if not root.is_dir():
            parser.error(f"{root} is not a directory")
        service, indexed = build_search_service(root, embedder)
        print(f"\n{name}: {len(indexed)} indexed files")
        for query, expected in queries:
            missing = [path for path in expected if not (root / path).is_file()]
            if missing:
                parser.error(f"{name}: expected files missing: {missing}")
            paths = repolens_top_paths(service, query, 5)
            hits = [path for path in expected if path in paths]
            print(f"  {query!r}: expected={list(expected)} hits={hits} results={list(paths)}")


if __name__ == "__main__":
    main()

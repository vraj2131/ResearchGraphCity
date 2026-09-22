from __future__ import annotations

import json

from app.openalex_snapshot import OpenAlexSnapshot


def test_snapshot_resolves_ids_and_serves_search_and_citation_candidates(tmp_path):
    works = [
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/seed",
            "title": "Graph learning seed",
            "topics": [{"display_name": "Graph Learning"}],
            "referenced_works": [],
        },
        {
            "id": "https://openalex.org/W2",
            "doi": None,
            "title": "Fast graph neural networks",
            "topics": [{"display_name": "Graph Learning"}],
            "referenced_works": ["https://openalex.org/W1"],
        },
        {
            "id": "https://openalex.org/W3",
            "doi": None,
            "title": "Clinical evidence synthesis",
            "topics": [{"display_name": "Medicine"}],
            "referenced_works": [],
        },
    ]
    path = tmp_path / "works.jsonl"
    path.write_text("".join(json.dumps(work) + "\n" for work in works), encoding="utf-8")
    snapshot = OpenAlexSnapshot(path)

    assert snapshot.resolve_seed("W1").work["title"] == "Graph learning seed"
    assert [work["id"] for work in snapshot.iter_citing_works("W1", limit=10)] == ["https://openalex.org/W2"]
    assert [work["id"] for work in snapshot.iter_works({"search": "graph neural"}, limit=2)] == [
        "https://openalex.org/W2",
        "https://openalex.org/W1",
    ]

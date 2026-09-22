from __future__ import annotations

from pathlib import Path

from ..storage import read_json


CITY_NAMES = {"research": "Research Graph City", "seeded": "Seeded Research Graph City"}


class JsonCityRepository:
    def __init__(self, processed_dir: Path):
        self.processed_dir = processed_dir

    def _file(self, city_id: str, suffix: str) -> Path:
        if city_id not in CITY_NAMES:
            raise KeyError(city_id)
        return self.processed_dir / f"{city_id}_{suffix}.json"

    def list_cities(self) -> list[dict]:
        result = [{"city_type": "research", "name": CITY_NAMES["research"]}]
        if self._file("seeded", "buildings").exists():
            result.append({"city_type": "seeded", "name": CITY_NAMES["seeded"]})
        return result

    def read_collection(self, city_id: str, suffix: str) -> list[dict]:
        return read_json(self._file(city_id, suffix), [])

    def get_scene(self, city_id: str) -> dict[str, list[dict]]:
        return {
            suffix: self.read_collection(city_id, suffix)
            for suffix in ("buildings", "bridges", "streets", "communities")
        }

    def get_building(self, city_id: str, building_id: str) -> dict | None:
        return self._find(city_id, "buildings", "building_id", building_id)

    def get_bridge(self, city_id: str, bridge_id: str) -> dict | None:
        return self._find(city_id, "bridges", "bridge_id", bridge_id)

    def get_street(self, city_id: str, street_id: str) -> dict | None:
        return self._find(city_id, "streets", "street_id", street_id)

    def get_building_papers(
        self, city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None
    ) -> list[dict]:
        vertex_ids = self._building_vertex_ids(city_id, building_id, floor_id)
        papers = [item for item in self.read_collection(city_id, "vertices") if item.get("paper_id") in vertex_ids]
        return self._page(papers, "paper_id", limit, cursor)

    def get_building_edges(
        self, city_id: str, building_id: str, floor_id: str | None = None, limit: int = 200, cursor: str | None = None
    ) -> list[dict]:
        vertex_ids = self._building_vertex_ids(city_id, building_id, floor_id)
        edges = [
            item
            for item in self.read_collection(city_id, "edges")
            if item.get("source") in vertex_ids and item.get("target") in vertex_ids
        ]
        return self._enrich_edges(city_id, self._page_edges(edges, limit, cursor))

    def get_bridge_edges(self, city_id: str, bridge_id: str, limit: int = 200, cursor: str | None = None) -> list[dict]:
        bridge = self.get_bridge(city_id, bridge_id)
        if bridge is None:
            raise KeyError(bridge_id)
        source_ids = self._building_vertex_ids(city_id, bridge["source_building_id"])
        target_ids = self._building_vertex_ids(city_id, bridge["target_building_id"])
        edges = [
            item
            for item in self.read_collection(city_id, "edges")
            if (item.get("source") in source_ids and item.get("target") in target_ids)
            or (item.get("source") in target_ids and item.get("target") in source_ids)
        ]
        return self._enrich_edges(city_id, self._page_edges(edges, limit, cursor))

    def _find(self, city_id: str, suffix: str, key: str, value: str) -> dict | None:
        return next((item for item in self.read_collection(city_id, suffix) if item.get(key) == value), None)

    def _building_vertex_ids(self, city_id: str, building_id: str, floor_id: str | None = None) -> set[str]:
        building = self.get_building(city_id, building_id)
        if building is None:
            raise KeyError(building_id)
        if floor_id is None:
            return set(building.get("vertex_ids", []))
        for floor in building.get("floors", []):
            if floor.get("floor_id") == floor_id:
                return set(floor.get("vertex_ids", []))
        raise KeyError(floor_id)

    def _paper_refs(self, city_id: str) -> dict[str, dict]:
        return {
            item["paper_id"]: {
                key: item[key]
                for key in ("paper_id", "title", "publication_year", "venue")
                if item.get(key) is not None
            }
            for item in self.read_collection(city_id, "vertices")
            if item.get("paper_id")
        }

    def _enrich_edges(self, city_id: str, edges: list[dict]) -> list[dict]:
        refs = self._paper_refs(city_id)
        result = []
        for item in edges:
            edge = dict(item)
            if edge.get("source") in refs:
                edge["source_paper"] = refs[edge["source"]]
            if edge.get("target") in refs:
                edge["target_paper"] = refs[edge["target"]]
            result.append(edge)
        return result

    @staticmethod
    def _page(items: list[dict], key: str, limit: int, cursor: str | None) -> list[dict]:
        bounded = max(1, min(limit, 200))
        ordered = sorted(items, key=lambda item: str(item.get(key, "")))
        if cursor:
            ordered = [item for item in ordered if str(item.get(key, "")) > cursor]
        return ordered[:bounded]

    @staticmethod
    def _page_edges(items: list[dict], limit: int, cursor: str | None) -> list[dict]:
        bounded = max(1, min(limit, 200))
        ordered = sorted(items, key=lambda item: (str(item.get("source", "")), str(item.get("target", ""))))
        if cursor:
            ordered = [item for item in ordered if f"{item.get('source', '')}:{item.get('target', '')}" > cursor]
        return ordered[:bounded]

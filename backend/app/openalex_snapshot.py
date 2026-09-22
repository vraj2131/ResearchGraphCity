from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterator

from .openalex_client import OpenAlexClient, ResolvedSeed


class OpenAlexSnapshot:
    """Local JSONL-backed OpenAlex client for predictable large builds."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._works: dict[str, dict] | None = None
        self._citing: dict[str, list[dict]] | None = None

    def _load(self) -> None:
        if self._works is not None:
            return
        works: dict[str, dict] = {}
        citing: dict[str, list[dict]] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                work = json.loads(line)
                openalex_id = OpenAlexClient.extract_openalex_id(str(work.get("id") or ""))
                if not openalex_id:
                    continue
                works[openalex_id] = work
                for referenced in work.get("referenced_works") or []:
                    target = OpenAlexClient.extract_openalex_id(str(referenced))
                    if target:
                        citing.setdefault(target, []).append(work)
        self._works = works
        self._citing = citing

    def resolve_seed(self, raw_input: str) -> ResolvedSeed:
        self._load()
        assert self._works is not None
        value = raw_input.strip()
        openalex_id = OpenAlexClient.extract_openalex_id(value)
        if openalex_id:
            return ResolvedSeed(value, "openalex_id", self._works.get(openalex_id))
        doi = OpenAlexClient.extract_doi(value)
        if doi:
            work = next(
                (
                    item
                    for item in self._works.values()
                    if OpenAlexClient.extract_doi(str(item.get("doi") or "")) == doi
                ),
                None,
            )
            return ResolvedSeed(value, "doi", work)
        normalized = _tokens(value)
        ranked = sorted(
            self._works.values(),
            key=lambda item: (-len(normalized & _tokens(str(item.get("title") or ""))), str(item.get("id") or "")),
        )
        return ResolvedSeed(value, "title", ranked[0] if ranked and normalized & _tokens(ranked[0].get("title", "")) else None)

    def fetch_works_by_ids(self, openalex_ids: list[str]) -> Iterator[dict]:
        self._load()
        assert self._works is not None
        for value in dict.fromkeys(openalex_ids):
            openalex_id = OpenAlexClient.extract_openalex_id(value)
            if openalex_id and openalex_id in self._works:
                yield self._works[openalex_id]

    def iter_citing_works(self, openalex_id: str, *, limit: int) -> Iterator[dict]:
        self._load()
        assert self._citing is not None
        normalized = OpenAlexClient.extract_openalex_id(openalex_id)
        for work in self._citing.get(normalized or "", [])[:limit]:
            yield work

    def iter_works(self, filters: dict, *, limit: int, per_page: int = 100) -> Iterator[dict]:
        del per_page
        self._load()
        assert self._works is not None
        query = _tokens(str(filters.get("search") or ""))
        ranked = []
        for work in self._works.values():
            searchable = _tokens(
                f"{work.get('title') or ''} "
                + " ".join(str(item.get("display_name") or "") for item in work.get("topics") or [])
            )
            score = len(query & searchable) if query else 1
            if score:
                ranked.append((score, str(work.get("id") or ""), work))
        for _, _, work in sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]:
            yield work


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2}

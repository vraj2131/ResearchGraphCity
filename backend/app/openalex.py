from __future__ import annotations

import os
import re
from typing import Iterable

import requests

from .config import load_project_env
from .graph_processing import SEED_QUERIES, build_research_edges, generate_research_city, normalize_openalex_work, write_processed_city


load_project_env()

OPENALEX_URL = "https://api.openalex.org/works"
SELECT_FIELDS = ",".join(
    [
        "id",
        "doi",
        "title",
        "abstract_inverted_index",
        "publication_year",
        "authorships",
        "primary_location",
        "topics",
        "keywords",
        "referenced_works",
        "cited_by_count",
        "open_access",
    ]
)


def fetch_openalex_works(
    queries: Iterable[str] = SEED_QUERIES,
    per_query: int = 100,
    target_total: int | None = None,
    continue_on_error: bool = False,
) -> list[dict]:
    api_key = os.getenv("OPENALEX_API_KEY")
    page_size = max(1, min(per_query, 100))
    seen: set[str] = set()
    works: list[dict] = []
    query_list = list(queries)
    if target_total is not None:
        cursors = {query: "*" for query in query_list}
        while any(cursors.values()) and len(works) < target_total:
            for query in query_list:
                cursor = cursors.get(query)
                if not cursor:
                    continue
                remaining = target_total - len(works)
                if remaining <= 0:
                    return works
                try:
                    payload = fetch_openalex_page(query, cursor, min(page_size, remaining), api_key)
                except RuntimeError:
                    if not continue_on_error:
                        raise
                    cursors[query] = None
                    continue
                results = payload.get("results", [])
                for work in results:
                    key = work_key(work)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    works.append(work)
                    if len(works) >= target_total:
                        return works
                cursors[query] = (payload.get("meta") or {}).get("next_cursor") if results else None
        return works

    for query in queries:
        cursor: str | None = "*"
        fetched_for_query = 0
        query_limit = per_query
        while cursor and fetched_for_query < query_limit:
            try:
                payload = fetch_openalex_page(query, cursor, min(page_size, query_limit - fetched_for_query), api_key)
            except RuntimeError:
                if not continue_on_error:
                    raise
                break
            results = payload.get("results", [])
            fetched_for_query += len(results)
            for work in results:
                key = work_key(work)
                if not key or key in seen:
                    continue
                seen.add(key)
                works.append(work)
            cursor = (payload.get("meta") or {}).get("next_cursor")
            if not results:
                break
    return works


def fetch_openalex_page(query: str, cursor: str, per_page: int, api_key: str | None) -> dict:
    params = {
        "search": query,
        "per_page": per_page,
        "cursor": cursor,
        "sort": "cited_by_count:desc",
        "select": SELECT_FIELDS,
    }
    if api_key:
        params["api_key"] = api_key
    try:
        response = requests.get(OPENALEX_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        raise RuntimeError(f"OpenAlex request failed for query '{query}'") from None
    return response.json()


def fetch_openalex_lookup(params: dict, description: str) -> dict:
    api_key = os.getenv("OPENALEX_API_KEY")
    request_params = {"select": SELECT_FIELDS, **params}
    if api_key:
        request_params["api_key"] = api_key
    try:
        response = requests.get(OPENALEX_URL, params=request_params, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        raise RuntimeError(f"OpenAlex seed lookup failed for {description}") from None
    return response.json()


def fetch_openalex_work_by_id(openalex_id: str) -> dict | None:
    api_key = os.getenv("OPENALEX_API_KEY")
    request_params = {"select": SELECT_FIELDS}
    if api_key:
        request_params["api_key"] = api_key
    work_id = openalex_id.rsplit("/", 1)[-1]
    try:
        response = requests.get(f"{OPENALEX_URL}/{work_id}", params=request_params, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except requests.RequestException:
        raise RuntimeError(f"OpenAlex seed lookup failed for {work_id}") from None
    return response.json()


def dedupe_works(works: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped = []
    for work in works:
        key = work_key(work)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(work)
    return deduped


def work_key(work: dict) -> str:
    return (work.get("doi") or work.get("id") or "").lower()


def parse_seed_text(seed_text: str) -> list[str]:
    seeds: list[str] = []
    seen: set[str] = set()
    for line in seed_text.splitlines():
        value = line.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        seeds.append(value)
    return seeds[:20]


def resolve_seed_works(seed_inputs: list[str]) -> tuple[list[dict], list[str]]:
    works: list[dict] = []
    warnings: list[str] = []
    for rank, seed_input in enumerate(seed_inputs, start=1):
        try:
            work = resolve_seed_work(seed_input)
        except RuntimeError as exc:
            warnings.append(f"Skipped seed '{seed_input}': {exc}")
            continue
        if not work:
            warnings.append(f"Skipped seed '{seed_input}': no OpenAlex match")
            continue
        work["_seed_input"] = seed_input
        work["_seed_rank"] = rank
        works.append(work)
    return dedupe_works(works), warnings


def resolve_seed_work(seed_input: str) -> dict | None:
    value = seed_input.strip()
    openalex_id = extract_openalex_work_id(value)
    if openalex_id:
        return fetch_openalex_work_by_id(openalex_id)
    doi = extract_doi(value)
    if doi:
        payload = fetch_openalex_lookup({"filter": f"doi:{doi}", "per_page": 1}, doi)
        results = payload.get("results") or []
        return results[0] if results else None
    payload = fetch_openalex_lookup({"search": value, "per_page": 1}, value)
    results = payload.get("results") or []
    return results[0] if results else None


def extract_openalex_work_id(value: str) -> str | None:
    match = re.search(r"(?:openalex\.org/)?(W\d+)$", value.strip(), flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def extract_doi(value: str) -> str | None:
    cleaned = value.strip()
    cleaned = cleaned.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    match = re.search(r"10\.\d{4,9}/\S+", cleaned, flags=re.IGNORECASE)
    return match.group(0).rstrip(".,;") if match else None


def seed_expansion_queries(seed_works: list[dict], seed_inputs: list[str]) -> list[str]:
    queries: list[str] = []
    for seed_input in seed_inputs:
        queries.append(seed_input)
    for work in seed_works:
        title = work.get("title")
        if title:
            queries.append(title)
        for topic in work.get("topics") or []:
            label = topic.get("display_name")
            if label:
                queries.append(label)
    return list(dict.fromkeys(query for query in queries if query))[:20]


def build_city_from_openalex(processed_dir, per_query: int = 100, target_total: int | None = None):
    raw_works = fetch_openalex_works(per_query=per_query, target_total=target_total)
    vertices = [normalize_openalex_work(work, idx + 1) for idx, work in enumerate(raw_works)]
    edges = build_research_edges(vertices)
    city = generate_research_city(vertices, edges)
    write_processed_city(city, processed_dir)
    return city


def build_city_from_seed_inputs(seed_inputs: list[str], processed_dir, target_total: int = 1000, per_query: int = 100):
    seeds = parse_seed_text("\n".join(seed_inputs))
    if not seeds:
        raise ValueError("At least one seed paper title, DOI, or OpenAlex work URL is required.")
    seed_works, warnings = resolve_seed_works(seeds)
    if not seed_works:
        seed_works = []
    remaining = max(0, target_total - len(seed_works))
    related_works = []
    if remaining > 0:
        related_works = fetch_openalex_works(seed_expansion_queries(seed_works, seeds), per_query=per_query, target_total=remaining, continue_on_error=True)
    raw_works = dedupe_works(seed_works + related_works)[:target_total]
    if not raw_works:
        raise RuntimeError("OpenAlex returned no works for the provided seed papers.")
    seed_metadata: dict[str, tuple[str, int]] = {}
    for fallback_rank, work in enumerate(seed_works, start=1):
        seed_metadata[work_key(work)] = (
            work.get("_seed_input") or seeds[min(fallback_rank - 1, len(seeds) - 1)],
            int(work.get("_seed_rank") or fallback_rank),
        )
    vertices = []
    for idx, work in enumerate(raw_works, start=1):
        vertex = normalize_openalex_work(work, idx)
        seed_info = seed_metadata.get(work_key(work))
        if seed_info:
            vertex.seeded = True
            vertex.seed_input = seed_info[0]
            vertex.seed_rank = seed_info[1]
            vertex.seed_relevance = 1.0
        vertices.append(vertex)
    edges = build_research_edges(vertices)
    city = generate_research_city(vertices, edges)
    city.warnings = warnings
    write_processed_city(city, processed_dir, prefix="seeded")
    return city

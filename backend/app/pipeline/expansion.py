from __future__ import annotations

from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil, log1p
import re
from typing import Callable, Iterable, Iterator
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..models import CityPaperRecord, CityRecord, PaperRecord, PaperReferenceRecord
from ..openalex_client import OpenAlexClient, OpenAlexCancelled
from ..repositories.postgres_city import PostgresCityRepository
from .persistence import upsert_openalex_work_batch


@dataclass(frozen=True)
class ExpansionCandidate:
    work: dict
    seed_openalex_id: str
    source: str
    domain: str
    components: dict[str, float]
    relevance: float
    depth: int


@dataclass(frozen=True)
class ExpansionResult:
    accepted_count: int
    total_paper_count: int
    exhausted: bool


def candidate_relevance(components: dict[str, float]) -> float:
    return round(
        0.40 * components["semantic_to_seed"]
        + 0.25 * components["citation_proximity"]
        + 0.20 * components["topic_overlap"]
        + 0.10 * components["source_quality"]
        + 0.05 * components["recency"],
        6,
    )


def balanced_candidates(
    candidates: Iterable[ExpansionCandidate],
    *,
    target: int,
    seed_count: int,
    seed_quota_factor: float = 1.25,
    domain_quota_fraction: float = 0.35,
) -> list[ExpansionCandidate]:
    if target <= 0:
        return []
    seed_quota = max(1, ceil(target / max(1, seed_count) * seed_quota_factor))
    domain_quota = max(1, ceil(target * domain_quota_fraction))
    ordered = sorted(candidates, key=lambda item: (-item.relevance, canonical_work_key(item.work)))
    selected: list[ExpansionCandidate] = []
    deferred: list[ExpansionCandidate] = []
    seen: set[str] = set()
    by_seed: Counter[str] = Counter()
    by_domain: Counter[str] = Counter()
    for candidate in ordered:
        key = canonical_work_key(candidate.work)
        if not key or key in seen or candidate.relevance <= 0 or not any(candidate.components.values()):
            continue
        seen.add(key)
        if by_seed[candidate.seed_openalex_id] >= seed_quota or by_domain[candidate.domain] >= domain_quota:
            deferred.append(candidate)
            continue
        selected.append(candidate)
        by_seed[candidate.seed_openalex_id] += 1
        by_domain[candidate.domain] += 1
        if len(selected) >= target:
            return selected
    for candidate in deferred:
        if len(selected) >= target:
            break
        selected.append(candidate)
    return selected


def stream_balanced_candidates(
    candidates: Iterable[ExpansionCandidate],
    *,
    target: int,
    seed_count: int,
    seed_quota_factor: float = 1.25,
    domain_quota_fraction: float = 0.35,
) -> Iterator[ExpansionCandidate]:
    """Yield quota-compliant candidates immediately, then redistribute unused quota."""
    if target <= 0:
        return
    seed_quota = max(1, ceil(target / max(1, seed_count) * seed_quota_factor))
    domain_quota = max(1, ceil(target * domain_quota_fraction))
    seen: set[str] = set()
    by_seed: Counter[str] = Counter()
    by_domain: Counter[str] = Counter()
    deferred: list[ExpansionCandidate] = []
    yielded = 0
    for candidate in candidates:
        key = canonical_work_key(candidate.work)
        if not key or key in seen or candidate.relevance <= 0 or not any(candidate.components.values()):
            continue
        seen.add(key)
        if by_seed[candidate.seed_openalex_id] >= seed_quota or by_domain[candidate.domain] >= domain_quota:
            if len(deferred) < target:
                deferred.append(candidate)
            continue
        yield candidate
        yielded += 1
        by_seed[candidate.seed_openalex_id] += 1
        by_domain[candidate.domain] += 1
        if yielded >= target:
            return
    for candidate in sorted(deferred, key=lambda item: (-item.relevance, canonical_work_key(item.work))):
        yield candidate
        yielded += 1
        if yielded >= target:
            return


def score_work_for_seed(work: dict, seed: PaperRecord, source: str, depth: int) -> ExpansionCandidate:
    candidate_topics = {item.get("display_name", "").casefold() for item in work.get("topics") or [] if item.get("display_name")}
    seed_topics = {item.casefold() for item in seed.topics}
    topic_overlap = jaccard(candidate_topics, seed_topics)
    candidate_tokens = tokenize((work.get("title") or "") + " " + " ".join(candidate_topics))
    seed_tokens = tokenize(seed.title + " " + " ".join(seed.topics))
    semantic = jaccard(candidate_tokens, seed_tokens)
    citation_proximity = (1.0 / max(1, depth)) if source in {"reference", "citation"} else 0.0
    source_quality = min(1.0, log1p(max(0, int(work.get("cited_by_count") or 0))) / 10.0)
    year = work.get("publication_year")
    current_year = datetime.now(timezone.utc).year
    recency = max(0.0, 1.0 - max(0, current_year - year) / 20.0) if isinstance(year, int) else 0.0
    components = {
        "semantic_to_seed": round(semantic, 6),
        "citation_proximity": round(citation_proximity, 6),
        "topic_overlap": round(topic_overlap, 6),
        "source_quality": round(source_quality, 6),
        "recency": round(recency, 6),
    }
    domain = next(iter(sorted(candidate_topics)), "general")
    return ExpansionCandidate(
        work=work,
        seed_openalex_id=seed.openalex_id,
        source=source,
        domain=domain,
        components=components,
        relevance=candidate_relevance(components),
        depth=depth,
    )


def expand_city(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    client: OpenAlexClient,
    *,
    cancel_check: Callable[[], bool] | None = None,
    batch_size: int = 2_000,
    workers: int = 1,
    on_batch_committed: Callable[[uuid.UUID, list[str]], None] | None = None,
) -> ExpansionResult:
    cancel_check = cancel_check or (lambda: False)
    with repository.session_factory() as session:
        city = session.get(CityRecord, city_id)
        if city is None:
            raise KeyError(str(city_id))
        seed_papers = session.scalars(
            select(PaperRecord)
            .join(CityPaperRecord, CityPaperRecord.openalex_id == PaperRecord.openalex_id)
            .where(CityPaperRecord.city_id == city_id, CityPaperRecord.is_seed.is_(True))
            .order_by(CityPaperRecord.seed_position)
        ).all()
        existing_rows = session.execute(
            select(CityPaperRecord.openalex_id, PaperRecord.doi)
            .join(PaperRecord, PaperRecord.openalex_id == CityPaperRecord.openalex_id)
            .where(CityPaperRecord.city_id == city_id)
        ).all()
        existing = {openalex_id for openalex_id, _ in existing_rows}
        existing_keys = {openalex_id.casefold() for openalex_id, _ in existing_rows}
        existing_keys.update(doi.casefold() for _, doi in existing_rows if doi)
        target_total = city.target_paper_count
    remaining = max(0, target_total - len(existing))
    if remaining == 0:
        return ExpansionResult(0, len(existing), False)
    if not seed_papers:
        raise ValueError("Seed stage must resolve at least one paper before expansion")

    raw_candidates = _candidate_streams(client, seed_papers, remaining)
    scored = (
        score_work_for_seed(work, seed, source, depth)
        for work, seed, source, depth in parallel_round_robin(
            raw_candidates,
            max_workers=workers,
            cancel_check=cancel_check,
        )
        if canonical_work_key(work) not in existing_keys
    )
    selected = stream_balanced_candidates(scored, target=remaining, seed_count=len(seed_papers))
    accepted = 0
    batch: list[ExpansionCandidate] = []
    for candidate in selected:
        batch.append(candidate)
        if len(batch) < batch_size:
            continue
        committed_ids = _persist_candidate_batch(city_id, repository, batch, len(existing), accepted, remaining)
        accepted += len(committed_ids)
        if on_batch_committed:
            on_batch_committed(city_id, committed_ids)
        batch = []
        if cancel_check():
            raise OpenAlexCancelled("City expansion cancelled")
    if batch:
        committed_ids = _persist_candidate_batch(city_id, repository, batch, len(existing), accepted, remaining)
        accepted += len(committed_ids)
        if on_batch_committed:
            on_batch_committed(city_id, committed_ids)
    total = len(existing) + accepted
    return ExpansionResult(accepted, total, total < target_total)


def _persist_candidate_batch(
    city_id: uuid.UUID,
    repository: PostgresCityRepository,
    batch: list[ExpansionCandidate],
    existing_count: int,
    accepted_count: int,
    target_remaining: int,
) -> list[str]:
    with repository.session_factory.begin() as session:
        indexed = [
            (existing_count + accepted_count + offset, candidate.work)
            for offset, candidate in enumerate(batch, start=1)
        ]
        vertices = upsert_openalex_work_batch(session, indexed)
        memberships = [
            {
                "city_id": city_id,
                "openalex_id": vertex.openalex_id,
                "external_paper_id": f"P_{existing_count + accepted_count + offset:06d}",
                "is_seed": False,
                "seed_relevance": candidate.relevance,
                "expansion_depth": candidate.depth,
                "expansion_source": candidate.source,
            }
            for offset, (candidate, vertex) in enumerate(zip(batch, vertices, strict=True), start=1)
        ]
        membership_insert = insert(CityPaperRecord).values(memberships)
        membership_excluded = membership_insert.excluded
        session.execute(
            membership_insert.on_conflict_do_update(
                index_elements=[CityPaperRecord.city_id, CityPaperRecord.openalex_id],
                set_={
                    "seed_relevance": membership_excluded.seed_relevance,
                    "expansion_depth": membership_excluded.expansion_depth,
                    "expansion_source": membership_excluded.expansion_source,
                },
            )
        )
        references = [
            {"source_openalex_id": vertex.openalex_id, "target_openalex_id": referenced_id}
            for vertex in vertices
            for referenced_id in vertex.referenced_paper_ids
            if referenced_id and referenced_id != vertex.openalex_id
        ]
        if references:
            session.execute(
                insert(PaperReferenceRecord).values(references).on_conflict_do_nothing(
                    index_elements=[PaperReferenceRecord.source_openalex_id, PaperReferenceRecord.target_openalex_id]
                )
            )
        city = session.get(CityRecord, city_id)
        new_accepted = accepted_count + len(batch)
        city.paper_count = existing_count + new_accepted
        city.configuration = {
            **city.configuration,
            "expansion_checkpoint": {"accepted": new_accepted, "target": target_remaining},
        }
    return [vertex.openalex_id for vertex in vertices]


def _candidate_streams(client: OpenAlexClient, seeds: list[PaperRecord], remaining: int):
    per_seed = max(100, ceil(remaining * 1.8 / len(seeds)))
    streams = []
    for seed in seeds:
        references = list((seed.metadata_json or {}).get("referenced_works", []))
        if references:
            streams.append(_tagged(client.fetch_works_by_ids(references), seed, "reference", 1))
        streams.append(_tagged(client.iter_citing_works(seed.openalex_id, limit=min(per_seed, 2_000)), seed, "citation", 1))
        queries = [seed.title, *seed.topics[:3]]
        for query in dict.fromkeys(item for item in queries if item):
            streams.append(
                _tagged(
                    client.iter_works({"search": query, "sort": "relevance_score:desc"}, limit=per_seed),
                    seed,
                    "semantic_search",
                    1,
                )
            )
    return streams


def _tagged(works: Iterable[dict], seed: PaperRecord, source: str, depth: int):
    for work in works:
        yield work, seed, source, depth


def round_robin(iterables: Iterable[Iterable]) -> Iterator:
    active = deque(iter(item) for item in iterables)
    while active:
        iterator = active.popleft()
        try:
            yield next(iterator)
            active.append(iterator)
        except StopIteration:
            continue


def parallel_round_robin(
    iterables: Iterable[Iterable],
    *,
    max_workers: int,
    cancel_check: Callable[[], bool] | None = None,
) -> Iterator:
    cancel_check = cancel_check or (lambda: False)
    active = [iter(item) for item in iterables]
    worker_count = max(1, max_workers)
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="openalex") as executor:
        while active:
            next_active = []
            for start in range(0, len(active), worker_count):
                if cancel_check():
                    raise OpenAlexCancelled("OpenAlex collection cancelled")
                batch = active[start : start + worker_count]
                futures = [executor.submit(_next_item, iterator) for iterator in batch]
                for iterator, future in zip(batch, futures, strict=True):
                    found, item = future.result()
                    if found:
                        yield item
                        next_active.append(iterator)
            active = next_active


def _next_item(iterator):
    try:
        return True, next(iterator)
    except StopIteration:
        return False, None


def canonical_work_key(work: dict) -> str:
    doi = work.get("doi")
    if isinstance(doi, str) and doi:
        return re.sub(r"^https?://doi\.org/", "", doi, flags=re.IGNORECASE).casefold()
    return str(work.get("id") or "").casefold()


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)

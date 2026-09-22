from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from .pipeline.embeddings import hash_documents
from .repositories.postgres_city import PostgresCityRepository
from .schemas import AssistantClaim, AssistantResponse, AssistantRouteStep


QUERY_STOP_WORDS = {
    "a", "about", "access", "and", "are", "available", "best", "city", "code", "data", "domain", "domains", "give", "i",
    "changed", "find", "has", "have", "how", "including", "inspect", "latest", "me", "open", "over", "paper", "papers",
    "recent", "research", "route", "should", "show", "the", "these", "through", "time", "to", "trend", "trends", "what", "which", "with",
}


def research_query_text(question: str) -> str:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]*", question.casefold())
    meaningful = [token for token in tokens if token not in QUERY_STOP_WORDS and not re.fullmatch(r"(?:19|20)\d{2}", token)]
    return " ".join(meaningful) or question.strip()


def infer_question_filters(question: str, explicit: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = {key: value for key, value in (explicit or {}).items() if value not in (None, "")}
    lowered = question.casefold()
    between = re.search(r"\bbetween\s+(19\d{2}|20\d{2})\s+and\s+(19\d{2}|20\d{2})\b", lowered)
    since = re.search(r"\b(?:since|after|from)\s+(19\d{2}|20\d{2})\b", lowered)
    before = re.search(r"\b(?:before|until|through)\s+(19\d{2}|20\d{2})\b", lowered)
    if between:
        filters.setdefault("year_min", int(between.group(1)))
        filters.setdefault("year_max", int(between.group(2)))
    if since:
        filters.setdefault("year_min", int(since.group(1)))
    if before:
        filters.setdefault("year_max", int(before.group(1)))
    if "recent" in lowered or "latest" in lowered:
        filters.setdefault("year_min", datetime.now(UTC).year - 5)
    if "open access" in lowered:
        filters.setdefault("open_access", True)
    if "code and data" in lowered or re.search(r"\b(?:with|has|including)\s+(?:available\s+)?code\b", lowered):
        filters.setdefault("code_available", True)
    if "code and data" in lowered or re.search(r"\b(?:with|has|including)\s+(?:available\s+)?data\b", lowered):
        filters.setdefault("data_available", True)
    return filters


def evidence_ids(packet: dict[str, Any]) -> set[str]:
    return {
        item["evidence_id"]
        for collection in ("papers", "buildings", "districts", "relationships", "timeline")
        for item in packet.get(collection, [])
        if item.get("evidence_id")
    }


def _route_targets(packet: dict[str, Any]) -> set[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for paper in packet.get("papers", []):
        targets.add(("paper", paper.get("paper_id", "")))
        if paper.get("building_id"):
            targets.add(("building", paper["building_id"]))
    for building in packet.get("buildings", []):
        targets.add(("building", building.get("building_id", "")))
    for district in packet.get("districts", []):
        targets.add(("community", district.get("district_id", "")))
    for relationship in packet.get("relationships", []):
        relationship_type = relationship.get("relationship_kind", "bridge")
        targets.add((relationship_type, relationship.get("relationship_id", "")))
    return targets


def _confidence(claims: list[AssistantClaim], packet: dict[str, Any]) -> float:
    known = evidence_ids(packet)
    if not claims or not known:
        return 0.0
    citation_count = sum(len(claim.citation_ids) for claim in claims)
    valid_count = sum(1 for claim in claims for citation in claim.citation_ids if citation in known)
    citation_coverage = valid_count / max(citation_count, 1)
    retrieval_margin = max(0.0, min(float(packet.get("retrieval_margin", 0.0)), 1.0))
    entity_validation = 1.0 if citation_count == valid_count else 0.0
    evidence_agreement = sum(claim.support_score for claim in claims) / max(len(claims), 1)
    return round(
        0.35 * citation_coverage
        + 0.25 * retrieval_margin
        + 0.20 * entity_validation
        + 0.20 * evidence_agreement,
        4,
    )


def validate_assistant_response(response: AssistantResponse, packet: dict[str, Any]) -> AssistantResponse:
    known = evidence_ids(packet)
    for claim in response.claims:
        unknown = [citation for citation in claim.citation_ids if citation not in known]
        if unknown:
            raise ValueError(f"Assistant cited unknown evidence ID: {unknown[0]}")

    valid_targets = _route_targets(packet)
    route_steps = [
        step for step in response.route_steps if (step.target_type, step.target_id) in valid_targets
    ]
    return response.model_copy(
        update={
            "papers": packet.get("papers", []),
            "buildings": packet.get("buildings", []),
            "districts": packet.get("districts", []),
            "relationships": packet.get("relationships", []),
            "timeline": packet.get("timeline", []),
            "route_steps": route_steps,
            "filters_applied": packet.get("filters_applied", {}),
            "retrieval_summary": packet.get("retrieval_summary", {}),
            "confidence": _confidence(response.claims, packet),
        }
    )


def build_retrieval_fallback(question: str, packet: dict[str, Any], reason: str | None = None) -> AssistantResponse:
    papers = packet.get("papers", [])
    buildings = packet.get("buildings", [])
    districts = packet.get("districts", [])
    timeline = packet.get("timeline", [])
    relationships = packet.get("relationships", [])
    claims = [
        AssistantClaim(
            claim=f'{paper["title"]} is a retrieved match in {paper.get("building_label") or "the city"}.',
            citation_ids=[paper["evidence_id"]],
            support_score=max(0.0, min(float(paper.get("score", 0.0)), 1.0)),
        )
        for paper in papers[:3]
    ]
    asks_trend = any(term in question.casefold() for term in ("trend", "over time", "changed", "growth"))
    if asks_trend and timeline:
        first, last = timeline[0], timeline[-1]
        peak = max(timeline, key=lambda item: item.get("paper_count", 0))
        answer = (
            f'This city spans {first["year"]} to {last["year"]}. Annual coverage changes from '
            f'{first["paper_count"]} papers to {last["paper_count"]}, with the largest represented year '
            f'at {peak["year"]} ({peak["paper_count"]} papers).'
        )
        claims.insert(
            0,
            AssistantClaim(
                claim=f'{peak["year"]} is the most represented publication year in this city.',
                citation_ids=[peak["evidence_id"]],
                support_score=1.0,
            ),
        )
    elif papers:
        building_names = ", ".join(item.get("label", item.get("building_id", "")) for item in buildings[:3])
        domain_names = ", ".join(dict.fromkeys(item.get("domain_name", "") for item in districts if item.get("domain_name")))
        answer = f"The strongest evidence is in {building_names or 'the retrieved buildings'}"
        if domain_names:
            answer += f" within {domain_names}"
        answer += ". The top papers are " + "; ".join(item["title"] for item in papers[:3]) + "."
    else:
        answer = f'No papers in this city matched "{question}" with the selected filters.'
    if reason:
        answer += f" LLM synthesis is unavailable: {reason}"
    route_steps = [
        AssistantRouteStep(
            label=building.get("label", building["building_id"]),
            target_type="building",
            target_id=building["building_id"],
            reason=f'Contains retrieved evidence for {building.get("domain_name") or "this question"}.',
        )
        for building in buildings[:3]
    ]
    for relationship in relationships[:2]:
        route_steps.append(
            AssistantRouteStep(
                label=f'{relationship["source_building_id"]} to {relationship["target_building_id"]}',
                target_type=relationship.get("relationship_kind", "bridge"),
                target_id=relationship["relationship_id"],
                reason="Follow this evidence-backed building relationship.",
            )
        )
    response = AssistantResponse(
        answer_markdown=answer,
        claims=claims,
        papers=papers,
        buildings=buildings,
        districts=districts,
        relationships=relationships,
        timeline=timeline,
        route_steps=route_steps,
        filters_applied=packet.get("filters_applied", {}),
        retrieval_summary=packet.get("retrieval_summary", {}),
        confidence=0.0,
        model_available=False,
    )
    return validate_assistant_response(response, packet)


def build_evidence_packet(
    repository: PostgresCityRepository,
    city_id: str,
    question: str,
    filters: dict[str, Any] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    filters = infer_question_filters(question, filters)
    retrieval_query = research_query_text(question)
    query_embedding = hash_documents([retrieval_query])[0].tolist()
    papers = repository.search_papers(
        city_id,
        retrieval_query,
        query_embedding,
        filters=filters,
        limit=max(1, min(limit, 30)),
    )
    buildings_by_id: dict[str, dict[str, Any]] = {}
    districts_by_id: dict[str, dict[str, Any]] = {}
    for paper in papers:
        if paper.get("building_id"):
            buildings_by_id.setdefault(
                paper["building_id"],
                {
                    "evidence_id": f'building:{paper["building_id"]}',
                    "building_id": paper["building_id"],
                    "label": paper.get("building_label") or paper["building_id"],
                    "district_id": paper.get("district_id"),
                    "domain_name": paper.get("domain_name"),
                },
            )
        if paper.get("district_id"):
            districts_by_id.setdefault(
                paper["district_id"],
                {
                    "evidence_id": f'district:{paper["district_id"]}',
                    "district_id": paper["district_id"],
                    "name": paper.get("district_name") or paper["district_id"],
                    "domain_name": paper.get("domain_name"),
                },
            )
        # Keep prompts bounded while preserving fields needed for paper questions.
        paper["abstract"] = paper.get("abstract", "")[:800]
        paper["authors"] = paper.get("authors", [])[:8]
        for field in ("topics", "keywords", "methods", "datasets", "institutions"):
            paper[field] = paper.get(field, [])[:8]

    relationships = repository.relationships_for_buildings(city_id, list(buildings_by_id), limit=12)
    timeline_data = repository.get_timeline(city_id)
    timeline = [
        {"evidence_id": f'timeline:{item["year"]}', **item}
        for item in timeline_data.get("years", [])
    ]
    scores = [float(item.get("score", 0.0)) for item in papers]
    top_score = scores[0] if scores else 0.0
    second_score = scores[1] if len(scores) > 1 else 0.0
    retrieval_margin = min(1.0, max(0.0, 0.5 * top_score + top_score - second_score))
    return {
        "question": question,
        "papers": papers,
        "buildings": list(buildings_by_id.values()),
        "districts": list(districts_by_id.values()),
        "relationships": relationships,
        "timeline": timeline,
        "filters_applied": filters,
        "retrieval_summary": {
            "returned_count": len(papers),
            "building_count": len(buildings_by_id),
            "district_count": len(districts_by_id),
            "relationship_count": len(relationships),
            "year_min": timeline_data.get("year_min"),
            "year_max": timeline_data.get("year_max"),
        },
        "retrieval_margin": round(retrieval_margin, 4),
    }


def answer_research_question(
    repository: PostgresCityRepository,
    provider: Any,
    city_id: str,
    question: str,
    filters: dict[str, Any] | None = None,
    limit: int = 12,
) -> AssistantResponse:
    packet = build_evidence_packet(repository, city_id, question, filters, limit)
    if not getattr(provider, "api_key", None):
        response = build_retrieval_fallback(question, packet, "GROQ_API_KEY is not configured")
    else:
        try:
            response = validate_assistant_response(provider.generate_assistant_answer(question, packet), packet)
        except Exception as exc:
            response = build_retrieval_fallback(question, packet, str(exc))
    conversation_id = repository.save_assistant_exchange(
        city_id,
        question,
        response,
        packet,
        getattr(provider, "model", None) if response.model_available else None,
    )
    return response.model_copy(update={"conversation_id": conversation_id})


def build_evidence_report(packet: dict[str, Any]) -> str:
    lines = [
        "# Research Graph City Evidence Report",
        "",
        f'**Question:** {packet.get("question", "")}',
        "",
        "## Retrieved Papers",
        "",
    ]
    for paper in packet.get("papers", []):
        metadata = " | ".join(
            str(value)
            for value in (paper.get("publication_year"), paper.get("venue"), paper.get("domain_name"))
            if value
        )
        lines.extend(
            [
                f'- **{paper.get("title", "Untitled")}** (`{paper.get("evidence_id")}`)',
                f"  {metadata}" if metadata else "",
                f'  Building: {paper.get("building_label") or paper.get("building_id") or "Unassigned"}',
            ]
        )
    lines.extend(["", "## Domains And Buildings", ""])
    for building in packet.get("buildings", []):
        lines.append(
            f'- **{building.get("label", building.get("building_id"))}**: '
            f'{building.get("domain_name") or "General Research"} (`{building.get("evidence_id")}`)'
        )
    lines.extend(["", "## Relationships", ""])
    for relationship in packet.get("relationships", []):
        lines.append(
            f'- {relationship.get("source_building_id")} to {relationship.get("target_building_id")}: '
            f'{relationship.get("relationship_kind")} score {relationship.get("score", 0):.3f} '
            f'(`{relationship.get("evidence_id")}`)'
        )
        for evidence in relationship.get("evidence", [])[:4]:
            lines.append(f"  - {evidence}")
    lines.extend(["", "## Publication Timeline", ""])
    for item in packet.get("timeline", []):
        lines.append(
            f'- {item.get("year")}: {item.get("paper_count", 0)} papers, '
            f'{item.get("citation_count", 0)} citations (`{item.get("evidence_id")}`)'
        )
    filters = packet.get("filters_applied", {})
    lines.extend(["", "## Retrieval", "", f"Filters: `{filters}`", f'Summary: `{packet.get("retrieval_summary", {})}`', ""])
    return "\n".join(line for line in lines if line is not None)

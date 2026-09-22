from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


CityType = Literal["research", "seeded"]


class ResearchVertex(BaseModel):
    paper_id: str
    openalex_id: str
    doi: str | None = None
    title: str
    abstract: str = ""
    publication_year: int | None = None
    authors: list[str] = Field(default_factory=list)
    author_ids: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    institution_ids: list[str] = Field(default_factory=list)
    venue: str = ""
    publisher: str = ""
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    referenced_paper_ids: list[str] = Field(default_factory=list)
    citation_count: int = 0
    open_access: bool = False
    code_available: bool = False
    data_available: bool = False
    embedding: list[float] = Field(default_factory=list)
    seeded: bool = False
    seed_input: str | None = None
    seed_rank: int | None = None
    seed_relevance: float = 0.0


class ResearchEdge(BaseModel):
    source: str
    target: str
    edge_type: str = "mixed"
    edge_weight: float
    components: dict[str, float]
    evidence: list[str] = Field(default_factory=list)
    directed_citation: bool = False


class Floor(BaseModel):
    floor_id: str
    building_id: str
    floor_index: int
    core_range: tuple[int, int]
    vertex_ids: list[str]
    node_count: int
    top_labels: list[str] = Field(default_factory=list)
    activation_score: float = 0.0
    summary: dict[str, Any] | None = None


class Building(BaseModel):
    building_id: str
    city_type: CityType = "research"
    vertex_ids: list[str]
    node_count: int
    edge_count: int
    internal_density: float
    avg_core: float
    max_core: int
    height: float
    footprint: float
    x: float
    z: float
    top_labels: list[str] = Field(default_factory=list)
    semantic_domain: str = "general"
    semantic_domain_name: str = "General Research"
    semantic_color: str = "#94a3b8"
    profile: dict[str, Any] = Field(default_factory=dict)
    original_labels: dict[str, list[str]] = Field(default_factory=dict)
    activation: dict[str, float] = Field(default_factory=dict)
    activation_score: float = 0.0
    floors: list[Floor] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
    community_id: str | None = None


class Bridge(BaseModel):
    bridge_id: str
    city_type: CityType = "research"
    source_building_id: str
    target_building_id: str
    bridge_strength: float
    bridge_type: str
    components: dict[str, float]
    evidence: list[str] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
    activation_score: float = 0.0


class Street(BaseModel):
    street_id: str
    city_type: CityType = "research"
    source_building_id: str
    target_building_id: str
    street_type: str = "navigation"
    distance: float
    street_score: float = 0.0
    components: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)


class Community(BaseModel):
    community_id: str
    city_type: CityType = "research"
    name: str
    building_ids: list[str]
    top_labels: list[str] = Field(default_factory=list)
    semantic_domain: str = "general"
    semantic_domain_name: str = "General Research"
    metrics: dict[str, float] = Field(default_factory=dict)
    summary: dict[str, Any] | None = None
    color: str


class ResearchCity(BaseModel):
    vertices: list[ResearchVertex]
    edges: list[ResearchEdge]
    buildings: list[Building]
    floors: list[Floor]
    bridges: list[Bridge]
    streets: list[Street] = Field(default_factory=list)
    communities: list[Community]
    outskirts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SeededCityRequest(BaseModel):
    seed_text: str
    target_total: int = Field(default=1000, ge=10, le=100000)
    per_query: int = Field(default=100, ge=1, le=100)


class SeededCityResponse(BaseModel):
    city_type: CityType = "seeded"
    counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class CreateCityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    seed_inputs: list[str] = Field(min_length=1, max_length=30)
    target_paper_count: int = Field(default=1000, ge=10, le=100000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("City name is required")
        return cleaned

    @field_validator("seed_inputs")
    @classmethod
    def clean_seed_inputs(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty seed input is required")
        return cleaned


class CityLifecycleResponse(BaseModel):
    city_id: str
    city_type: str
    name: str
    status: str
    target_paper_count: int
    seed_count: int
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class BuildJobResponse(BaseModel):
    job_id: str
    city_id: str
    status: str
    stage: str
    progress_current: int
    progress_total: int
    message: str
    cancel_requested: bool = False
    error: dict[str, Any] | None = None


class BuildingSummaryPacket(BaseModel):
    building_id: str
    city_type: CityType = "research"
    node_count: int
    edge_count: int
    internal_density: float
    avg_core: float
    top_labels: list[str] = Field(default_factory=list)
    dominant_attributes: dict[str, Any] = Field(default_factory=dict)
    activation_score: float = 0.0
    strongest_bridges: list[dict[str, Any]] = Field(default_factory=list)


class BridgeSummaryPacket(BaseModel):
    bridge_id: str
    city_type: CityType = "research"
    source_building_id: str
    target_building_id: str
    bridge_strength: float
    components: dict[str, float]
    evidence: list[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    short_name: str
    one_sentence_summary: str
    evidence_points: list[str]
    recommended_bridge_id: str | None = None
    confidence: float


class CityNavigationRequest(BaseModel):
    city_type: CityType = "seeded"
    question: str


class CityNavigationResponse(BaseModel):
    answer: str
    route_steps: list[dict[str, Any]] = Field(default_factory=list)
    focus_building_ids: list[str] = Field(default_factory=list)
    focus_bridge_ids: list[str] = Field(default_factory=list)
    confidence: float
    model_available: bool = True


class AssistantQueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=12, ge=1, le=30)


class CityCompareRequest(BaseModel):
    left_city_id: str
    right_city_id: str


class AssistantClaim(BaseModel):
    claim: str
    citation_ids: list[str] = Field(default_factory=list)
    support_score: float = Field(ge=0.0, le=1.0)


class AssistantRouteStep(BaseModel):
    label: str
    target_type: Literal["building", "bridge", "street", "community", "paper"]
    target_id: str
    reason: str


class AssistantResponse(BaseModel):
    conversation_id: str | None = None
    answer_markdown: str
    claims: list[AssistantClaim] = Field(default_factory=list)
    papers: list[dict[str, Any]] = Field(default_factory=list)
    buildings: list[dict[str, Any]] = Field(default_factory=list)
    districts: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    route_steps: list[AssistantRouteStep] = Field(default_factory=list)
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    retrieval_summary: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    model_available: bool = True

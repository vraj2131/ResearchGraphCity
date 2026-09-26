from __future__ import annotations

from datetime import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CityRecord(TimestampMixin, Base):
    __tablename__ = "cities"
    __table_args__ = (
        CheckConstraint("kind IN ('research', 'seeded')", name="ck_cities_kind"),
        CheckConstraint("status IN ('draft', 'building', 'ready', 'failed', 'cancelled')", name="ck_cities_status"),
        CheckConstraint("target_paper_count BETWEEN 10 AND 100000", name="ck_cities_target_paper_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    target_paper_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paper_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    building_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    district_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    algorithm_version: Mapped[str] = mapped_column(String(120), nullable=False, default="legacy-v1")
    embedding_model: Mapped[str] = mapped_column(String(240), nullable=False, default="tfidf-svd-64")
    source_version: Mapped[str] = mapped_column(String(120), nullable=False, default="openalex-api")
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CitySeedRecord(Base):
    __tablename__ = "city_seeds"
    __table_args__ = (UniqueConstraint("city_id", "position", name="uq_city_seeds_position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_openalex_id: Mapped[str | None] = mapped_column(Text)
    match_type: Mapped[str] = mapped_column(String(40), nullable=False, default="unresolved")
    match_score: Mapped[float | None] = mapped_column(Float)
    resolution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")


class PaperRecord(TimestampMixin, Base):
    __tablename__ = "papers"

    openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doi: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    publication_year: Mapped[int | None] = mapped_column(SmallInteger)
    venue: Mapped[str] = mapped_column(Text, nullable=False, default="")
    publisher: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    code_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    authors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    author_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    institutions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    institution_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    methods: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    datasets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


Index("uq_papers_normalized_doi", func.lower(PaperRecord.doi), unique=True, postgresql_where=PaperRecord.doi.is_not(None))
Index("ix_papers_search_vector", PaperRecord.search_vector, postgresql_using="gin")


class PaperEmbeddingRecord(Base):
    __tablename__ = "paper_embeddings"

    openalex_id: Mapped[str] = mapped_column(Text, ForeignKey("papers.openalex_id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(240), primary_key=True)
    dimensions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PaperNeighborRecord(Base):
    __tablename__ = "paper_neighbors"

    model: Mapped[str] = mapped_column(String(240), primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_openalex_id: Mapped[str] = mapped_column(
        Text, ForeignKey("papers.openalex_id", ondelete="CASCADE"), primary_key=True
    )
    target_openalex_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    similarities: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


Index("ix_paper_neighbors_source_fk", PaperNeighborRecord.source_openalex_id)


class CityPaperRecord(Base):
    __tablename__ = "city_papers"
    __table_args__ = (UniqueConstraint("city_id", "external_paper_id", name="uq_city_papers_external_id"),)

    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True)
    openalex_id: Mapped[str] = mapped_column(Text, ForeignKey("papers.openalex_id", ondelete="CASCADE"), primary_key=True)
    external_paper_id: Mapped[str] = mapped_column(String(120), nullable=False)
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seed_position: Mapped[int | None] = mapped_column(SmallInteger)
    seed_relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expansion_depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    expansion_source: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    building_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"))
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("floors.id", ondelete="SET NULL"))


Index("ix_city_papers_building", CityPaperRecord.city_id, CityPaperRecord.building_id)
Index("ix_city_papers_external_id", CityPaperRecord.city_id, CityPaperRecord.external_paper_id)
Index("ix_city_papers_seed_relevance", CityPaperRecord.city_id, CityPaperRecord.seed_relevance.desc())
Index("ix_city_papers_openalex_id", CityPaperRecord.openalex_id)
Index("ix_city_papers_floor_fk", CityPaperRecord.floor_id)
Index("ix_city_papers_building_fk", CityPaperRecord.building_id)


class PaperReferenceRecord(Base):
    __tablename__ = "paper_references"

    source_openalex_id: Mapped[str] = mapped_column(Text, ForeignKey("papers.openalex_id", ondelete="CASCADE"), primary_key=True)
    target_openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)


class PaperEdgeRecord(Base):
    __tablename__ = "paper_edges"
    __table_args__ = (
        UniqueConstraint("city_id", "source_openalex_id", "target_openalex_id", "edge_type", name="uq_paper_edges_pair_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    source_openalex_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_openalex_id: Mapped[str] = mapped_column(Text, nullable=False)
    edge_type: Mapped[str] = mapped_column(String(60), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    directed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


Index("ix_paper_edges_source", PaperEdgeRecord.city_id, PaperEdgeRecord.source_openalex_id)
Index("ix_paper_edges_target", PaperEdgeRecord.city_id, PaperEdgeRecord.target_openalex_id)


class DistrictRecord(TimestampMixin, Base):
    __tablename__ = "districts"
    __table_args__ = (UniqueConstraint("city_id", "external_id", name="uq_districts_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_domain: Mapped[str] = mapped_column(String(120), nullable=False, default="general")
    semantic_domain_name: Mapped[str] = mapped_column(Text, nullable=False, default="General Research")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#94a3b8")
    labels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(64))
    x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class BuildingRecord(TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("city_id", "external_id", name="uq_buildings_external_id"),
        UniqueConstraint("city_id", "id", name="uq_buildings_city_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    district_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("districts.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    internal_density: Mapped[float] = mapped_column(Float, nullable=False)
    avg_core: Mapped[float] = mapped_column(Float, nullable=False)
    max_core: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    footprint: Mapped[float] = mapped_column(Float, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    z: Mapped[float] = mapped_column(Float, nullable=False)
    top_labels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    semantic_domain: Mapped[str] = mapped_column(String(120), nullable=False, default="general")
    semantic_domain_name: Mapped[str] = mapped_column(Text, nullable=False, default="General Research")
    semantic_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#94a3b8")
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    original_labels: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(64))


class FloorRecord(Base):
    __tablename__ = "floors"
    __table_args__ = (
        UniqueConstraint("building_id", "floor_index", name="uq_floors_building_index"),
        UniqueConstraint("city_id", "building_id", "id", name="uq_floors_city_building_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(140), nullable=False)
    floor_index: Mapped[int] = mapped_column(Integer, nullable=False)
    core_min: Mapped[int] = mapped_column(Integer, nullable=False)
    core_max: Mapped[int] = mapped_column(Integer, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    top_labels: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    activation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    year_min: Mapped[int | None] = mapped_column(SmallInteger)
    year_max: Mapped[int | None] = mapped_column(SmallInteger)
    summary: Mapped[dict | None] = mapped_column(JSONB)


class BuildingPaperRecord(Base):
    """A paper can be a vertex of several connected edge fixed points."""
    __tablename__ = "building_papers"
    __table_args__ = (
        ForeignKeyConstraint(["city_id", "openalex_id"], ["city_papers.city_id", "city_papers.openalex_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["city_id", "building_id"], ["buildings.city_id", "buildings.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["city_id", "building_id", "floor_id"], ["floors.city_id", "floors.building_id", "floors.id"], ondelete="CASCADE"),
        Index("ix_building_papers_paper", "city_id", "openalex_id"),
        Index("ix_building_papers_floor_fk", "city_id", "building_id", "floor_id"),
    )
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)
    floor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FloorPaperRecord(Base):
    """All floor appearances, including endpoints shared across fragments."""
    __tablename__ = "floor_papers"
    __table_args__ = (
        ForeignKeyConstraint(["city_id", "building_id", "openalex_id"], ["building_papers.city_id", "building_papers.building_id", "building_papers.openalex_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["city_id", "building_id", "floor_id"], ["floors.city_id", "floors.building_id", "floors.id"], ondelete="CASCADE"),
        Index("ix_floor_papers_membership", "city_id", "building_id", "openalex_id"),
    )
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)
    building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class DecompositionEdgeRecord(Base):
    """Canonical undirected edge ownership, independent of research edge types."""
    __tablename__ = "decomposition_edges"
    __table_args__ = (
        ForeignKeyConstraint(["city_id", "building_id", "source_openalex_id"], ["building_papers.city_id", "building_papers.building_id", "building_papers.openalex_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["city_id", "building_id", "target_openalex_id"], ["building_papers.city_id", "building_papers.building_id", "building_papers.openalex_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["city_id", "building_id", "floor_id"], ["floors.city_id", "floors.building_id", "floors.id"], ondelete="CASCADE"),
        Index("ix_decomposition_edges_building", "city_id", "building_id", "floor_id"),
        Index("ix_decomposition_edges_target_fk", "city_id", "building_id", "target_openalex_id"),
    )
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source_openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_openalex_id: Mapped[str] = mapped_column(Text, primary_key=True)
    building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    floor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    peel: Mapped[int] = mapped_column(Integer, nullable=False)
    wave: Mapped[int] = mapped_column(Integer, nullable=False)
    fragment: Mapped[int] = mapped_column(Integer, nullable=False)
    wave_component: Mapped[int] = mapped_column(Integer, nullable=False)


class BuildingRelationshipRecord(Base):
    __tablename__ = "building_relationships"
    __table_args__ = (UniqueConstraint("city_id", "external_id", name="uq_relationships_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    source_building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    target_building_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    relationship_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    distance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    components: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    activation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[dict | None] = mapped_column(JSONB)


class CommunityRunRecord(Base):
    __tablename__ = "community_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CitySnapshotRecord(Base):
    __tablename__ = "city_snapshots"
    __table_args__ = (UniqueConstraint("city_id", "year", name="uq_city_snapshots_year"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    aggregates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class BuildJobRecord(Base):
    __tablename__ = "build_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_build_jobs_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    stage: Mapped[str] = mapped_column(String(60), nullable=False, default="resolve")
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="Queued")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(240))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict | None] = mapped_column(JSONB)


Index("ix_build_jobs_claim", BuildJobRecord.status, BuildJobRecord.created_at)


class IngestionCacheRecord(Base):
    __tablename__ = "ingestion_cache"

    request_fingerprint: Mapped[str] = mapped_column(String(128), primary_key=True)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    etag: Mapped[str | None] = mapped_column(Text)
    source_status: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssistantConversationRecord(Base):
    __tablename__ = "assistant_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    city_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssistantMessageRecord(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnswerCitationRecord(Base):
    __tablename__ = "answer_citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    support_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

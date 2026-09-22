from __future__ import annotations

from sqlalchemy.orm import Session

from ..graph_processing import normalize_openalex_work
from ..models import PaperRecord
from .bulk_io import upsert_paper_rows


def upsert_openalex_work(session: Session, work: dict, index: int) -> tuple[PaperRecord, object]:
    vertex = normalize_openalex_work(work, index)
    if not vertex.openalex_id:
        raise ValueError("OpenAlex work is missing its canonical ID")
    paper = session.get(PaperRecord, vertex.openalex_id)
    if paper is None:
        paper = PaperRecord(openalex_id=vertex.openalex_id, title=vertex.title)
        session.add(paper)
    paper.doi = vertex.doi
    paper.title = vertex.title
    paper.abstract = vertex.abstract
    paper.publication_year = vertex.publication_year
    paper.venue = vertex.venue
    paper.publisher = vertex.publisher
    paper.citation_count = vertex.citation_count
    paper.open_access = vertex.open_access
    paper.code_available = vertex.code_available
    paper.data_available = vertex.data_available
    paper.authors = vertex.authors
    paper.author_ids = vertex.author_ids
    paper.institutions = vertex.institutions
    paper.institution_ids = vertex.institution_ids
    paper.topics = vertex.topics
    paper.keywords = vertex.keywords
    paper.methods = vertex.methods
    paper.datasets = vertex.datasets
    paper.metadata_json = {
        "source": "openalex",
        "referenced_works": vertex.referenced_paper_ids,
    }
    return paper, vertex


def upsert_openalex_work_batch(session: Session, indexed_works: list[tuple[int, dict]]) -> list[object]:
    vertices = [normalize_openalex_work(work, index) for index, work in indexed_works]
    if any(not vertex.openalex_id for vertex in vertices):
        raise ValueError("OpenAlex work is missing its canonical ID")
    values = [
        {
            "openalex_id": vertex.openalex_id,
            "doi": vertex.doi,
            "title": vertex.title,
            "abstract": vertex.abstract,
            "publication_year": vertex.publication_year,
            "venue": vertex.venue,
            "publisher": vertex.publisher,
            "citation_count": vertex.citation_count,
            "open_access": vertex.open_access,
            "code_available": vertex.code_available,
            "data_available": vertex.data_available,
            "authors": vertex.authors,
            "author_ids": vertex.author_ids,
            "institutions": vertex.institutions,
            "institution_ids": vertex.institution_ids,
            "topics": vertex.topics,
            "keywords": vertex.keywords,
            "methods": vertex.methods,
            "datasets": vertex.datasets,
            "metadata": {"source": "openalex", "referenced_works": vertex.referenced_paper_ids},
        }
        for vertex in vertices
    ]
    upsert_paper_rows(session.connection(), values)
    return vertices

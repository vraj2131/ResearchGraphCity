#!/usr/bin/env python3
"""Generate the Research Graph City progress report PDF.

This intentionally uses only the Python standard library so the report can be
rebuilt on machines without pandoc, wkhtmltopdf, reportlab, or LibreOffice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "research_graph_city_progress_report.pdf"


@dataclass(frozen=True)
class Line:
    text: str
    size: int = 11
    indent: int = 0
    gap_before: int = 0
    bold: bool = False


def title(text: str) -> Line:
    return Line(text=text, size=22, gap_before=8, bold=True)


def subtitle(text: str) -> Line:
    return Line(text=text, size=13, gap_before=4)


def h1(text: str) -> Line:
    return Line(text=text, size=16, gap_before=16, bold=True)


def h2(text: str) -> Line:
    return Line(text=text, size=13, gap_before=10, bold=True)


def para(text: str) -> Line:
    return Line(text=text, size=11, gap_before=5)


def bullet(text: str) -> Line:
    return Line(text="- " + text, size=10, indent=14, gap_before=3)


def metric(name: str, definition: str) -> Line:
    return Line(text=f"{name}: {definition}", size=10, indent=8, gap_before=4)


REPORT: list[Line] = [
    title("Research Graph City Progress Report"),
    subtitle("Project progress summary and future roadmap, July to September 2026"),
    para(
        "This report summarizes the Research Graph City prototype built as a sibling app to the original "
        "Graph-Cities project. The goal was to transform research-paper graphs into a navigable 3D city "
        "where paper clusters become buildings, dense substructure becomes floors, and cross-topic "
        "relationships become bridges or streets."
    ),
    h1("Executive Summary"),
    bullet(
        "Created a new full-stack app in ResearchGraphCity without modifying Graph_City_Web."
    ),
    bullet(
        "Implemented OpenAlex ingestion, graph construction, building/floor/bridge/street generation, "
        "FastAPI endpoints, and a React Three Fiber city renderer."
    ),
    bullet(
        "Scaled the default research city from a 300-paper first slice to a 1000-paper dataset while "
        "keeping the existing inspector, summaries, and rendering behavior working."
    ),
    bullet(
        "Added seeded-city generation so a user can paste a small list of papers and build a new city from "
        "related OpenAlex papers."
    ),
    bullet(
        "Integrated Groq for structured JSON summaries and navigation answers, with graceful unavailable "
        "states when keys or network access are missing."
    ),
    h1("Current Data"),
    h2("Default Research City"),
    bullet(
        "Seed queries: graph visualization, GraphRAG, and education income mobility."
    ),
    bullet(
        "Current processed scale: 1000 papers, 6457 paper-level graph edges, 13 buildings, 65 floors, "
        "5 strong bridges, 12 streets, and 8 semantic communities."
    ),
    h2("Seeded City"),
    bullet(
        "Input: simple textarea where each line is a paper title, DOI, or OpenAlex URL."
    ),
    bullet(
        "Pipeline: resolve seed papers, expand through related OpenAlex works, dedupe, then run the same "
        "graph-city rules as the default city."
    ),
    bullet(
        "Latest verified seeded run: 991 papers, 7668 graph edges, 12 buildings, 32 floors, 7 bridges, "
        "11 streets, and 8 communities."
    ),
    h2("Paper Metadata Used"),
    bullet(
        "OpenAlex ID, DOI, title, abstract-derived inverted index, publication year, venue, topics, "
        "keywords, authors, institutions, references, citation count, open-access signal, code/data signal, "
        "and seed provenance."
    ),
    h1("Backend Work Completed"),
    bullet(
        "Added FastAPI and Pydantic schemas for vertices, edges, buildings, floors, bridges, streets, "
        "communities, summaries, seeded-city requests, and navigation responses."
    ),
    bullet(
        "Updated OpenAlex access to the current api.openalex.org API style, including API-key support, "
        "per-page limits, seed lookup, deduplication by DOI and OpenAlex ID, and cache-friendly JSON output."
    ),
    bullet(
        "Built paper-level edges from citations, topic overlap, venue overlap, author/institution overlap, "
        "method/dataset overlap, abstract/title text similarity, and temporal proximity."
    ),
    bullet(
        "Generated buildings from NetworkX graph structure using community detection and core-number signals. "
        "Small or isolated groups are preserved as outskirts rather than being lost."
    ),
    bullet(
        "Generated floors from core-number bands, with a fallback split so buildings with uniform core values "
        "still display visible floors."
    ),
    bullet(
        "Generated bridges for strong cross-building relationships and streets for weaker but still nonzero "
        "research relationships. Zero-score layout fallback streets were removed from the inspectable data."
    ),
    bullet(
        "Exposed APIs for city metadata, buildings, bridges, streets, communities, building details, paper "
        "nodes, internal edges, bridge cross edges, seeded-city generation, and LLM summaries/navigation."
    ),
    h1("Frontend Work Completed"),
    bullet(
        "Built a Vite, React, TypeScript, React Three Fiber, Zustand, and Tailwind frontend."
    ),
    bullet(
        "Rendered buildings as stacked cylindrical/frustum floors, with labels, grid navigation, zoom controls, "
        "camera interaction, bridges, streets, layer toggles, and selected-item highlighting."
    ),
    bullet(
        "Added building, bridge, street, and paper-node inspectors with metrics, original labels, paper titles, "
        "internal edges, cross edges, floor filters, and relationship evidence."
    ),
    bullet(
        "Added building interior mode so users can inspect paper nodes and edges inside a selected building "
        "without crowding the main city view."
    ),
    bullet(
        "Changed internal and cross-edge displays from opaque R_000001 IDs to paper titles plus metadata, "
        "making the evidence readable during demos."
    ),
    bullet(
        "Added summary-word selection so a word selected in a generated building summary highlights matching "
        "labels from the building's original data."
    ),
    bullet(
        "Added a simple seeded-city panel with a sample button and clearer errors for OpenAlex/network/key "
        "failures."
    ),
    h1("Visual Semantics"),
    bullet("Building: a cluster/community of related papers."),
    bullet("Footprint: number of papers in the building."),
    bullet("Height: structural importance from core score plus paper count."),
    bullet("Floor: a core-number band inside that building."),
    bullet("Base color family: semantic domain, such as health, networks, economics, biology, or AI."),
    bullet(
        "Shade variation: separate communities within the same semantic domain get related but distinguishable "
        "colors, reducing repeated identical building domains."
    ),
    bullet("Floor shade: higher-activation floors appear stronger within the building color family."),
    bullet("Glow: activation score only. It does not change semantic color or building size."),
    bullet("Bridge: a strong cross-building research relationship."),
    bullet("Street: a weaker, nonzero relationship that still helps explain city navigation."),
    bullet("Amber ring and label outline: currently selected building, bridge, street, or paper node."),
    h1("Metric Definitions"),
    metric(
        "Profile similarity",
        "0.30 J(topics) + 0.20 J(methods) + 0.15 J(datasets) + 0.10 J(venues) + "
        "0.10 J(institutions), where J is Jaccard similarity.",
    ),
    metric(
        "Semantic similarity",
        "0.50 J(building labels) + 0.50 J(profile topics and keywords).",
    ),
    metric(
        "Cross-edge strength",
        "min(1, cross_building_edge_count / sqrt(source_node_count * target_node_count)).",
    ),
    metric(
        "Vertex overlap",
        "J(vertices_A, vertices_B). This is normally 0 because buildings are disjoint paper sets.",
    ),
    metric(
        "Activation similarity",
        "1 - abs(activation_A - activation_B). Higher means the two buildings have similar current activity.",
    ),
    metric(
        "Activation score",
        "0.55 * recency + 0.45 * citation_signal, where recency = exp(-age/5) and "
        "citation_signal = min(1, average_citations / 100).",
    ),
    metric(
        "LLM confidence",
        "A structured-output confidence field returned by Groq for summaries or navigation. It is treated as "
        "a model self-assessment and should later be calibrated against retrieval evidence.",
    ),
    h1("LLM Integration"),
    bullet(
        "Groq is called through its OpenAI-compatible API and asked to return structured JSON, not free-form "
        "text that the app has to guess how to parse."
    ),
    bullet(
        "The LLM receives compact evidence packets: city index, selected building metrics, representative "
        "labels, representative papers, and bridge/street evidence. Raw full graph data is not sent."
    ),
    bullet(
        "The city navigator can answer a research question and return focused building IDs, bridge IDs, route "
        "steps, confidence, and model availability."
    ),
    h1("Quality And Verification"),
    bullet(
        "Backend tests cover OpenAlex normalization, deduplication, edge formulas, building/floor generation, "
        "bridge thresholds, street generation, seeded-city generation, and Groq JSON parsing."
    ),
    bullet(
        "Frontend tests cover API loading, visual mappings, layer toggles, inspectors, labels, selection "
        "highlighting, seeded-city controls, and navigation behavior."
    ),
    bullet(
        "Latest verification before this report: 40 backend tests passed, 32 frontend tests passed, and the "
        "frontend production build passed."
    ),
    h1("Key Design Decisions"),
    bullet(
        "The main 3D scene stays at building level so the city remains readable at 1000 papers. Paper nodes "
        "appear only in focused interior or inspector views."
    ),
    bullet(
        "Color represents semantic meaning. Activation is shown with glow and shade, not by changing domain "
        "identity."
    ),
    bullet(
        "Bridges and streets are separated because they answer different questions: bridges show strong "
        "research relationships, while streets preserve weaker contextual routes."
    ),
    bullet(
        "Inspectors expose original labels and paper titles so summaries and visual links are traceable back "
        "to data."
    ),
    h1("What Could Be Done Next"),
    h2("Data And Graph Quality"),
    bullet(
        "Add embedding-based similarity for titles and abstracts to improve semantic edges beyond token "
        "overlap."
    ),
    bullet(
        "Separate citation direction from similarity edges so influence and topical relatedness can be viewed "
        "independently."
    ),
    bullet(
        "Improve seeded expansion with user-controlled breadth, depth, year range, and relatedness thresholds."
    ),
    bullet(
        "Cache OpenAlex responses and store build provenance so every city can be reproduced."
    ),
    h2("Community And Layout"),
    bullet(
        "Add hierarchical communities: districts, neighborhoods, buildings, floors, and paper nodes."
    ),
    bullet(
        "Add a toggle between semantic-domain colors and modularity/community colors."
    ),
    bullet(
        "Implement a more faithful Graph City street-layout pass using research relevance as the road weight, "
        "then compare it against the current bridges-and-streets representation."
    ),
    bullet(
        "Improve placement so related buildings cluster into district-like groups and labels collide less."
    ),
    h2("User Workflows"),
    bullet(
        "Add a small pre-city seed graph preview for the initial 10 papers before expanding to a 1000-paper "
        "city."
    ),
    bullet(
        "Add paper search, filters by year/topic/venue, and one-click jump from search results to the "
        "corresponding building."
    ),
    bullet(
        "Add saved tours and exportable evidence reports for presentations."
    ),
    h2("LLM And Evaluation"),
    bullet(
        "Add retrieval over paper abstracts for deeper answers inside a building or across a bridge."
    ),
    bullet(
        "Calibrate LLM confidence against evidence coverage and require citations from selected paper titles."
    ),
    bullet(
        "Add evaluator tests for navigation quality on known seed sets and known research questions."
    ),
    h2("Production Readiness"),
    bullet(
        "Run seeded-city builds as background jobs rather than blocking an API request."
    ),
    bullet("Persist multiple user-generated cities with shareable IDs."),
    bullet("Add deployment configuration, monitoring, retry logic, and rate-limit handling."),
    bullet("Split frontend bundles so Three.js-heavy views load only when needed."),
    h1("Conclusion"),
    para(
        "Research Graph City now demonstrates the core concept: a research-paper graph can become a navigable "
        "3D city with meaningful buildings, floors, bridges, streets, colors, labels, and LLM-guided inspection. "
        "The next phase should focus on stronger graph semantics, better spatial layout, deeper retrieval, "
        "and workflows for creating and comparing multiple seeded cities."
    ),
]


def escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_line(line: Line) -> list[Line]:
    width = max(30, int((86 - line.indent * 0.35) * 11 / line.size))
    wrapped = textwrap.wrap(
        line.text,
        width=width,
        break_long_words=False,
        replace_whitespace=True,
    )
    if not wrapped:
        return [line]
    out = [Line(wrapped[0], line.size, line.indent, line.gap_before, line.bold)]
    for part in wrapped[1:]:
        prefix = "  " if line.text.startswith("- ") else ""
        out.append(Line(prefix + part, line.size, line.indent, 1, line.bold))
    return out


def layout_pages(lines: list[Line]) -> list[list[Line]]:
    pages: list[list[Line]] = []
    current: list[Line] = []
    y = 760
    bottom = 58
    for source in lines:
        for line in wrap_line(source):
            y -= line.gap_before
            line_height = int(line.size * 1.45)
            if y - line_height < bottom:
                pages.append(current)
                current = []
                y = 760
            current.append(line)
            y -= line_height
    if current:
        pages.append(current)
    return pages


def text_stream(page_lines: list[Line], page_number: int, page_count: int) -> bytes:
    commands: list[str] = []
    y = 760
    for line in page_lines:
        y -= line.gap_before
        font = "F2" if line.bold else "F1"
        x = 54 + line.indent
        commands.append(
            f"BT /{font} {line.size} Tf {x} {y} Td ({escape_pdf(line.text)}) Tj ET"
        )
        y -= int(line.size * 1.45)
    commands.append(
        f"BT /F1 8 Tf 54 32 Td (Research Graph City Progress Report) Tj ET"
    )
    commands.append(
        f"BT /F1 8 Tf 506 32 Td (Page {page_number} of {page_count}) Tj ET"
    )
    return ("\n".join(commands) + "\n").encode("latin-1", errors="replace")


def build_pdf(lines: list[Line]) -> bytes:
    pages = layout_pages(lines)
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    font_regular_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_ids: list[int] = []
    content_ids: list[int] = []
    for index, page_lines in enumerate(pages, start=1):
        stream = text_stream(page_lines, index, len(pages))
        content_id = add(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"endstream"
        )
        page_id = add(b"")
        content_ids.append(content_id)
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode(
        "ascii"
    )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>"
    ).encode("ascii")

    for page_id, content_id in zip(page_ids, content_ids):
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def main() -> None:
    OUTPUT.write_bytes(build_pdf(REPORT))
    print(OUTPUT)


if __name__ == "__main__":
    main()

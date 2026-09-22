from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


OUT = Path("ResearchGraphCity_5min_presentation.docx")

content = [
    ("title", "Research Graph City: 5-Minute Presentation Script"),
    ("heading", "0:00-0:30 - Problem"),
    (
        "p",
        "Research graphs are usually shown as node-link diagrams, but once there are hundreds of papers, those diagrams become hard to interpret. Our idea is to turn a research graph into a city. Papers become the underlying graph nodes, clusters of related papers become buildings, dense substructures become floors, and relationships between research areas become bridges or roads.",
    ),
    ("heading", "0:30-1:10 - Current Data"),
    (
        "p",
        "Right now we are using OpenAlex research paper data. We start small with three seed queries: graph visualization, GraphRAG, and education income mobility. For each query, we ingest up to 100 works, so the current processed graph has 300 papers.",
    ),
    ("p", "The current city contains 300 paper vertices, 1,776 paper-to-paper edges, 9 buildings, 45 floors, 6 bridges, and 8 communities."),
    (
        "p",
        "Each paper includes metadata like title, DOI/OpenAlex ID, abstract if available, year, venue, topics, keywords, authors, institutions, references, and citation count.",
    ),
    ("heading", "1:10-2:00 - How The Graph City Is Built"),
    (
        "p",
        "We create edges between papers using multiple signals: citation links, topic overlap, venue overlap, author or institution overlap, and text similarity from titles and abstracts. So two papers can be connected because they cite each other, discuss similar topics, appear in the same venue, share authors or institutions, or are semantically similar.",
    ),
    (
        "p",
        "Then we use graph algorithms to form the city. Communities and connected clusters become buildings. Core number is used to understand how central or dense papers are inside a building. Floors represent bands of core strength. Bridges are created when two buildings have enough cross-building similarity or paper-level cross edges.",
    ),
    ("heading", "2:00-3:30 - Live Demo Flow"),
    (
        "p",
        "First, I will show the 3D city view. Each building is a research cluster. Bigger buildings represent more papers. Taller or more layered buildings reflect stronger internal structure. Colors represent semantic communities, not random colors.",
    ),
    ("bullet", "Show the full city."),
    ("bullet", "Zoom in/out and rotate."),
    ("bullet", "Toggle labels, floors, bridges, and activation glow."),
    ("bullet", "Point out that buildings vary by paper count and structure."),
    (
        "p",
        "Now I will click a building. The inspector shows the number of papers, internal edges, density, average core, activation, and community ID.",
    ),
    (
        "p",
        "Density means how tightly connected the papers inside the building are. Average core measures how central or structurally embedded the papers are. Activation is a visual emphasis score showing how important or active this building is in the current city.",
    ),
    ("bullet", "Click a building."),
    ("bullet", "Show metrics."),
    ("bullet", "Show generated summary."),
    ("bullet", "Click words in the summary to highlight matching original labels."),
    ("bullet", "Show original labels grouped by topic or keyword."),
    ("bullet", "Click Inspect paper labels."),
    ("bullet", "Show actual paper titles, year, venue, topics, and keywords."),
    ("heading", "3:30-4:25 - Edges And Bridges"),
    (
        "p",
        "Next, I will show internal edges. These are paper-to-paper relationships inside a building. Earlier this showed only IDs like R_000010, but now it shows paper titles first, with IDs underneath only as debug references.",
    ),
    ("bullet", "Click Internal Edges."),
    ("bullet", "Show title-to-title relationships."),
    ("bullet", "Point out edge weight and evidence labels like topic similarity or semantic neighbor."),
    (
        "p",
        "Now I will click a bridge. Bridges connect buildings. The inspector shows which two buildings are connected, shared labels, cross edges, and component scores.",
    ),
    ("bullet", "Click a bridge or road."),
    ("bullet", "Show cross edges."),
    ("bullet", "Point out title-to-title paper relationships across buildings."),
    (
        "bullet",
        "Explain: These cross edges are what justify the bridge. They contribute to cross-edge strength, which is part of the bridge strength score and also helps the generated bridge summary.",
    ),
    ("heading", "4:25-5:00 - What This Enables"),
    (
        "p",
        "The main benefit is that instead of reading a flat graph, we can navigate research areas spatially. We can see large fields, dense subtopics, central papers, cross-domain bridges, and original evidence behind every visual object.",
    ),
    (
        "p",
        "This is currently a first slice: small OpenAlex dataset, real graph construction, real 3D rendering, searchable inspectable buildings, floors, labels, internal edges, cross edges, and LLM-ready evidence packets. The next step is scaling the dataset and adding richer search and paper-level detail workflows.",
    ),
    ("heading", "Quick Live Checklist"),
    ("bullet", "Full 3D city overview."),
    ("bullet", "Zoom and rotate."),
    ("bullet", "Toggle floors, labels, bridges, and activation."),
    ("bullet", "Click building."),
    ("bullet", "Explain papers, density, average core, and activation."),
    ("bullet", "Show original labels."),
    ("bullet", "Click summary word to highlight labels."),
    ("bullet", "Click Inspect paper labels."),
    ("bullet", "Click Internal Edges."),
    ("bullet", "Click bridge and show Cross Edges."),
    ("heading", "One-Line Summary"),
    (
        "p",
        "We turn a research paper graph from OpenAlex into an explorable 3D city where buildings are research clusters, floors show graph core structure, and bridges reveal cross-domain paper relationships.",
    ),
]


def paragraph(kind: str, text: str) -> str:
    text = escape(text)
    if kind == "title":
        props = '<w:pPr><w:pStyle w:val="Title"/></w:pPr>'
    elif kind == "heading":
        props = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    elif kind == "bullet":
        props = '<w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
    else:
        props = ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
""".format(body="\n".join(paragraph(kind, text) for kind, text in content))

styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:uiPriority w:val="34"/><w:qFormat/><w:pPr><w:ind w:left="720"/></w:pPr></w:style>
</w:styles>
"""

numbering_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
"""

content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
"""

now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Research Graph City 5-Minute Presentation</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""

app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>
"""

with ZipFile(OUT, "w", ZIP_DEFLATED) as docx:
    docx.writestr("[Content_Types].xml", content_types)
    docx.writestr("_rels/.rels", rels)
    docx.writestr("word/document.xml", document_xml)
    docx.writestr("word/styles.xml", styles_xml)
    docx.writestr("word/numbering.xml", numbering_xml)
    docx.writestr("word/_rels/document.xml.rels", doc_rels)
    docx.writestr("docProps/core.xml", core)
    docx.writestr("docProps/app.xml", app)

print(OUT.resolve())

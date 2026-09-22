# Research Graph City 100K Platform Design

**Date:** 2026-09-17

**Status:** Proposed for implementation

## Objective

Evolve Research Graph City from a synchronous, JSON-backed 1,000-paper prototype into a PostgreSQL-backed research discovery platform that can:

- accept 20 to 30 seed papers as titles, DOIs, or OpenAlex URLs;
- resolve the seed set and preview its original graph before expansion;
- acquire and process as many as 100,000 related papers;
- construct explainable paper, building, district, floor, bridge, and street structures;
- support search, filters, temporal exploration, city comparison, and evidence export;
- answer broad research questions about domains, papers, authors, methods, datasets, relationships, and trends;
- preserve every existing 1,000-paper city feature while the new system is introduced;
- leave `Graph-Cities/Graph_City_Web` unchanged.

The 100,000-paper target means 100,000 distinct normalized papers stored for one city. It does not mean rendering 100,000 Three.js meshes at once. The city view remains aggregate-first and retrieves paper-level detail on demand.

## Current-State Findings

The current application is a useful prototype with these constraints:

- `POST /api/cities/seeded/build` performs ingestion and graph generation inside one HTTP request.
- `SeededCityRequest.target_total` is limited to 1,000.
- Every city is stored in seven JSON files and API requests repeatedly scan those files.
- The current 1,000-paper research city occupies about 10 MB for vertices and edges; both research and seeded processed data occupy about 23 MB.
- Paper embeddings are 64-dimensional TF-IDF/SVD vectors created independently for each build.
- Graph construction and NetworkX community detection operate in one Python process.
- The frontend loads every building, bridge, street, and community before rendering.
- Paper nodes are loaded only when entering a building, which is the correct interaction pattern to retain.
- The Groq navigator receives a compact list of at most tens of buildings and bridges. It can recommend a path, but it cannot retrieve arbitrary paper-level evidence.

Simply changing `target_total` from 1,000 to 100,000 would create a long blocking request, repeated full-file scans, high peak memory, weak restart behavior, and an LLM context that cannot cover the corpus.

## Architectural Approach

Use PostgreSQL as the system of record and `pgvector` for semantic retrieval. Use a separate Python worker process and a PostgreSQL job table for background builds. The API creates jobs, reports progress, serves completed aggregate city geometry, and pages paper-level data. This avoids requiring Redis while still allowing multiple workers through `FOR UPDATE SKIP LOCKED` job claiming.

The architecture is split into four implementation programs:

1. **Persistence and jobs:** PostgreSQL, migrations, repositories, city/job lifecycle, legacy JSON import.
2. **Scalable graph science:** staged OpenAlex expansion, embeddings, sparse edge construction, hierarchical communities, metrics, temporal snapshots, and aggregate geometry.
3. **Research assistant:** hybrid retrieval, evidence packets, Groq structured answers, citations, and confidence derived from evidence coverage.
4. **Research workflows and rendering:** seed preview, build progress, search/filter, hierarchy, time, comparison, evidence export, and level-of-detail rendering.

Each program must produce working software independently. The existing JSON backend remains a compatibility fallback until PostgreSQL parity tests pass.

## Technology Decisions

### Database

- PostgreSQL 16 or newer.
- `pgvector` extension for paper and aggregate embeddings.
- SQLAlchemy 2.0 for typed persistence boundaries.
- Psycopg 3 as the PostgreSQL driver.
- Alembic for versioned migrations.
- PostgreSQL full-text search for lexical retrieval.
- HNSW cosine indexes for semantic retrieval after the initial bulk load.

`pgvector` supports exact and approximate nearest-neighbor search, HNSW indexes, half-precision vectors, and hybrid use with PostgreSQL full-text search. HNSW provides the appropriate read-time speed/recall trade-off for interactive research queries at the requested scale.

### Background Work

- A standalone command, `python -m app.worker`, runs one or more workers.
- Workers claim jobs in PostgreSQL with `SELECT ... FOR UPDATE SKIP LOCKED`.
- Each pipeline stage commits durable checkpoints and counters.
- A failed worker can resume from the last completed stage without reacquiring already stored papers.
- Cancellation is cooperative: the worker checks `cancel_requested_at` between pages and stages.

### Embeddings

- Store the embedding model identifier and dimension with every embedding.
- Use a scientific-document embedding provider behind a local interface.
- The default production model must be configurable through `EMBEDDING_MODEL`.
- Tests use a deterministic local fake provider and never download a model.
- The existing 64-dimensional TF-IDF/SVD embedding remains a fallback for offline development, but production builds use one corpus-independent embedding space so papers and questions are comparable across cities.

### External Data

- OpenAlex remains the canonical metadata and citation source.
- API calls use an API key, selected fields, cursor pagination, retry with jitter, and durable response caching.
- Seed resolution records exact, DOI, OpenAlex-ID, and title-search match provenance.
- For repeated or larger builds, the design allows a future OpenAlex snapshot/Parquet loader without changing repository interfaces.

## PostgreSQL Data Model

All primary identifiers are UUIDs except canonical OpenAlex IDs. Every city-owned table includes `city_id` to make city deletion, comparison, and authorization explicit.

### Core Tables

`cities`

- `id uuid primary key`
- `name text not null`
- `kind text check (kind in ('research', 'seeded'))`
- `status text check (status in ('draft', 'building', 'ready', 'failed', 'cancelled'))`
- `target_paper_count integer check (target_paper_count between 10 and 100000)`
- `paper_count`, `edge_count`, `building_count`, `district_count` integers
- `algorithm_version`, `embedding_model`, `source_version` text
- `configuration jsonb not null`
- `created_at`, `updated_at`, `completed_at` timestamptz

`city_seeds`

- `city_id uuid references cities on delete cascade`
- `position smallint`
- `raw_input text`
- `resolved_openalex_id text null`
- `match_type text`
- `match_score real null`
- `resolution_status text`
- unique `(city_id, position)`

`papers`

- `openalex_id text primary key`
- `doi text null`
- `title text not null`
- `abstract text not null default ''`
- `publication_year smallint null`
- `venue`, `publisher` text
- `citation_count integer not null default 0`
- `open_access`, `code_available`, `data_available` boolean
- `authors`, `author_ids`, `institutions`, `institution_ids`, `topics`, `keywords`, `methods`, `datasets` jsonb
- `search_vector tsvector`
- `metadata jsonb`
- unique partial index on normalized DOI where DOI is present

`paper_embeddings`

- `openalex_id text references papers on delete cascade`
- `model text`
- `dimensions smallint`
- `embedding vector`
- `created_at timestamptz`
- primary key `(openalex_id, model)`
- HNSW cosine expression index for the configured production model and dimension

`city_papers`

- `city_id uuid references cities on delete cascade`
- `openalex_id text references papers`
- `is_seed boolean`
- `seed_position smallint null`
- `seed_relevance real`
- `expansion_depth smallint`
- `expansion_source text`
- `building_id uuid null`
- `floor_id uuid null`
- primary key `(city_id, openalex_id)`
- indexes on `(city_id, building_id)`, `(city_id, publication_year)`, and `(city_id, seed_relevance desc)`

`paper_references`

- `source_openalex_id text references papers`
- `target_openalex_id text`
- primary key `(source_openalex_id, target_openalex_id)`

`paper_edges`

- `id bigint generated always as identity primary key`
- `city_id uuid references cities on delete cascade`
- `source_openalex_id`, `target_openalex_id` text
- `edge_type text`
- `weight real`
- `components jsonb`
- `evidence jsonb`
- `directed boolean`
- unique `(city_id, source_openalex_id, target_openalex_id, edge_type)`
- indexes on both city/source and city/target

### City Structure Tables

`districts` stores broad hierarchical communities and their metrics, labels, semantic domain, color, embedding, and layout position.

`buildings` stores district membership, node/edge counts, density, core statistics, activation, semantic fields, embedding, layout geometry, profile, original labels, and quality metrics.

`floors` stores building membership, floor index, core range, paper count, labels, activation, and time range. Floor membership remains on `city_papers`; arrays of all paper IDs are not stored in aggregate rows.

`building_relationships` stores both bridges and streets with a `relationship_kind` discriminator, source and target building IDs, score, component scores, evidence, activation, and whether the relationship passes the strong-bridge threshold.

`community_runs` stores algorithm, parameters, random seed, modularity, conductance summary, semantic cohesion, stability score, and completion time. This makes clustering reproducible and comparable.

`city_snapshots` stores year cutoffs and aggregate counts so temporal views can be served without rebuilding the entire graph on every slider movement.

### Operations And LLM Tables

`build_jobs`

- `id uuid primary key`
- `city_id uuid references cities on delete cascade`
- `status text check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled'))`
- `stage text`
- `progress_current`, `progress_total` integers
- `message text`
- `attempts smallint`
- `locked_by text null`
- `locked_at`, `heartbeat_at`, `cancel_requested_at`, `created_at`, `started_at`, `finished_at` timestamptz
- `error jsonb null`

`ingestion_cache` stores request fingerprints, response JSON, ETag where available, retrieval time, expiry, and source status.

`assistant_conversations` and `assistant_messages` store user questions, structured answer metadata, selected city scope, and model metadata.

`answer_citations` links each answer claim to a paper, building, district, bridge, or street with a supporting excerpt or numeric evidence record.

## Seeded Expansion To 100,000 Papers

### Input Contract

- Accept 1 to 30 non-empty lines.
- Each line can be a paper title, DOI, or OpenAlex work URL/ID.
- The UI recommends 20 to 30 seeds for a 100,000-paper build but permits smaller tests.
- Duplicate inputs are normalized and reported, not silently treated as separate seeds.
- The target count is selectable from 1,000, 10,000, 25,000, 50,000, and 100,000.

### Expansion Stages

1. **Resolve:** resolve every input and store match provenance and unresolved warnings.
2. **Preview:** create the seed-only citation/semantic graph immediately and expose it before expansion starts.
3. **Collect depth 1:** retrieve direct references, citing works where supported, semantically related works, and high-confidence topic/search results for each seed.
4. **Score candidates:** combine seed embedding similarity, citation distance, topic overlap, and source diversity.
5. **Collect depth 2+:** expand from high-scoring frontier papers in balanced batches until the target or source exhaustion.
6. **Deduplicate:** OpenAlex ID first, then normalized DOI; retain provenance from every route by which a paper was discovered.
7. **Balance:** prevent one seed or one OpenAlex topic from consuming the entire corpus by applying per-seed and per-domain soft quotas. Unused quota is redistributed.
8. **Persist:** upsert every page and checkpoint counters before requesting the next page.
9. **Embed:** embed only papers missing the configured model embedding.
10. **Build graph and city:** construct sparse edges and hierarchical aggregates.

Candidate relevance is:

`R(p) = 0.40 * semantic_to_seed + 0.25 * citation_proximity + 0.20 * topic_overlap + 0.10 * source_quality + 0.05 * recency`

The stored component values remain inspectable. A paper is never presented as related without at least one nonzero evidence component.

### Rate And Failure Behavior

- Respect OpenAlex authentication, current API limits, and retry guidance.
- Exponential backoff applies to 429 and retryable 5xx responses.
- A build can finish below target with a warning if the eligible related corpus is exhausted.
- Invalid seeds do not fail the entire job when at least one seed resolves.
- All source errors and skipped seeds are visible in the job and city provenance views.

## Scalable Graph Construction

An all-pairs comparison is forbidden: 100,000 papers would require roughly five billion pairs.

Candidate edge generation uses the union of bounded sources:

- exact citation links within the city;
- top `K_semantic = 20` approximate nearest neighbors from pgvector per paper;
- top `K_topic = 10` peers sampled from shared high-specificity topics;
- exact shared-author/method/dataset candidates with frequency caps;
- seed-to-seed links retained regardless of final weight.

Each undirected pair is canonicalized once. Citation edges preserve direction in a separate field. Edge weights continue exposing components, but semantic similarity uses corpus-independent embeddings and topic terms are weighted by inverse city frequency.

The default retained degree is capped at 40 non-citation similarity edges per paper after scoring. Citation edges are retained separately. This bounds interactive graph size while preserving explicit citation evidence.

Graph stages stream database rows in partitions. For algorithms requiring an in-memory graph, use compressed integer node IDs and process per connected component or district candidate. A 100,000-paper build must not materialize paper abstracts or full Pydantic objects for every edge simultaneously.

## Hierarchical Community Model

The hierarchy is:

`city -> district -> building -> floor -> paper`

- **Districts** are broad semantic groups created from a graph of provisional buildings.
- **Buildings** are paper communities detected from the sparse paper graph.
- **Floors** are core-number or time/core bands inside a building.
- **Papers** remain available only in focused views and paged inspectors.

Leiden is the default community algorithm because the pipeline needs a scalable, reproducible partition with a resolution parameter. Louvain remains available as a comparison baseline. The original Graph City-inspired building/floor/street mapping remains the visualization transform applied after research communities are computed.

Every community run records:

- modularity;
- per-community conductance;
- semantic cohesion from mean embedding similarity to centroid;
- size distribution and outlier count;
- stability under five seeded reruns, measured with adjusted mutual information;
- algorithm, resolution, random seed, and software version.

Oversized buildings are recursively split when they exceed the configured render/detail ceiling and improve both conductance and semantic cohesion. Tiny communities are merged only when a neighboring community passes a semantic and graph-connectivity threshold; otherwise they remain outskirts.

## Metric Semantics

Existing metrics remain available and gain versioned definitions.

- **Density:** internal observed undirected edges divided by `n(n-1)/2` for a building with `n > 1`.
- **Core:** k-core number computed on the building's internal unweighted projection; weighted coreness may be added as a separate metric and never silently substituted.
- **Profile similarity:** weighted similarity across normalized topics, methods, datasets, venues, institutions, and temporal profile.
- **Semantic similarity:** cosine similarity between aggregate embeddings, mapped to `[0,1]`.
- **Cross-edge strength:** normalized sum of cross-building edge weights, with raw count and normalized value both exposed.
- **Vertex overlap:** Jaccard overlap of paper membership; normally zero for a hard partition and meaningful for optional overlapping topic views.
- **Activation similarity:** `1 - abs(a-b)` for normalized building activation scores.
- **Activation:** a versioned combination of recency, citation velocity, newly added papers, and user-selected query relevance.
- **Assistant confidence:** evidence coverage and retrieval quality, not model self-confidence alone.

Metric definitions, formula versions, and component values are returned by the API so UI explanations never drift from backend computation.

## Bridges, Streets, And Original Graph City Semantics

- A **bridge** is a strong evidence-backed relationship between buildings.
- A **street** is a weaker but still nonzero research relationship used for navigation and context.
- No zero-score layout-only relationship is stored or shown as research evidence.
- Layout-only geometry, if needed to make districts navigable, is marked `visual_only` and excluded from inspectors, summaries, and research claims.
- Bridge and street evidence includes representative cross-paper edges, shared labels, semantic score, profile score, and citation direction counts.

The original Graph City contribution is retained as the mapping from graph structure to city structure: communities become buildings, core layers become floors, and inter-community connectivity becomes roads. The research-specific pipeline strengthens the graph definition and makes each transformation inspectable.

## Temporal Model

Temporal views use publication year and optionally OpenAlex update/citation history when available.

- The API serves year bounds and precomputed yearly aggregate snapshots.
- The frontend slider changes aggregate visibility and metrics without downloading all papers.
- Buildings are classified as emerging, stable, growing, or declining from paper-count and citation-velocity trends.
- Citation direction allows influence flow from older to newer communities.
- Time-based claims always identify the time window and metric used.

## Research Assistant And Retrieval

The assistant supports questions about:

- which domain, district, building, or floor covers a topic;
- which papers, authors, institutions, venues, methods, or datasets are relevant;
- why papers or buildings are connected;
- influential, recent, open-access, code-available, or data-available papers;
- changes over time;
- differences between two cities or communities;
- routes through the city when spatial navigation is useful.

### Retrieval Pipeline

1. Parse the question into structured filters and intent.
2. Run hybrid retrieval over PostgreSQL full-text rank and pgvector cosine similarity.
3. Retrieve matching papers plus their buildings, districts, representative edges, and relevant metrics.
4. Expand only one graph hop when the question asks for relationships.
5. Rerank and cap the evidence packet.
6. Ask Groq for schema-constrained JSON grounded only in that packet.
7. Validate every returned entity ID and citation against retrieved evidence.
8. Return the answer, claims, citations, related entities, optional city route, and evidence-derived confidence.

The assistant response contains:

- `answer_markdown`
- `claims[]` with `claim`, `citation_ids`, and `support_score`
- `papers[]`, `buildings[]`, `districts[]`, and `relationships[]`
- optional `route_steps[]`
- `filters_applied`
- `retrieval_summary`
- `confidence`
- `model_available`

Confidence is:

`C = 0.35 * citation_coverage + 0.25 * retrieval_margin + 0.20 * entity_validation + 0.20 * evidence_agreement`

If Groq is unavailable, retrieval results and evidence remain usable; only answer synthesis is marked unavailable. The application never hides search results because the LLM failed.

## API Design

### City Lifecycle

- `POST /api/cities` creates a draft seeded city from 1 to 30 inputs and target up to 100,000.
- `GET /api/cities/{city_id}` returns metadata, status, counts, provenance, and available year range.
- `POST /api/cities/{city_id}/build` queues a build and returns `202` with `job_id`.
- `GET /api/jobs/{job_id}` returns stage, progress, warnings, and errors.
- `POST /api/jobs/{job_id}/cancel` requests cancellation.
- `GET /api/cities/{city_id}/seed-graph` returns the resolved seed-only graph as soon as resolution finishes.

The existing `POST /api/cities/seeded/build` remains temporarily and delegates to create/queue for compatibility. It returns a deprecation header and job ID rather than blocking for a completed 100,000-paper city.

### Aggregate City Queries

- `GET /api/cities/{city_id}/scene?year=&domain=&min_score=` returns districts, buildings, bridges, and streets only.
- `GET /api/cities/{city_id}/districts/{district_id}` returns district metrics and paged buildings.
- Existing building, bridge, street, community, paper, and edge routes remain compatible where their payload is bounded.
- Large lists use cursor pagination with a maximum page size of 200.

### Search And Analysis

- `GET /api/cities/{city_id}/papers/search`
- `GET /api/cities/{city_id}/papers/{openalex_id}`
- `GET /api/cities/{city_id}/buildings/{building_id}/papers`
- `GET /api/cities/{city_id}/buildings/{building_id}/edges`
- `GET /api/cities/{city_id}/timeline`
- `POST /api/cities/compare`
- `POST /api/cities/{city_id}/assistant/query`
- `POST /api/cities/{city_id}/exports/evidence-report`

Search parameters include text, year range, domain, district, building, author, institution, venue, topic, open access, code available, data available, sort, cursor, and page size.

## Frontend Design

### Seed Workflow

The existing simple textarea remains. It adds:

- detected input count and duplicate warnings;
- target-size selector;
- resolved/unresolved seed results;
- seed-only graph preview;
- explicit Build City command;
- progress stages and cancellation;
- navigation away and later return to a running job.

### City Workspace

The first screen remains the actual city, not a landing page. The left panel gains compact search and filters. The right inspector supports districts, buildings, floors, papers, bridges, streets, and assistant citations.

The scene renders only bounded aggregates:

- default city view: districts/buildings/relationships;
- district focus: buildings in one district;
- building interior: a sampled or paged paper graph;
- no mode creates one mesh per paper for all 100,000 papers.

Three.js instancing is used for repeated building/floor/paper geometry. Labels use distance- and selection-aware budgets. API responses include stable geometry so the same city does not rearrange between sessions.

### Analytical Workflows

- Search result selects and frames its building, then optionally enters the paper.
- Edge-type controls distinguish citation, semantic, author, institution, method, and dataset relationships.
- Timeline slider shows city evolution and trend classifications.
- Compare mode shows shared and unique domains/buildings/papers between two cities.
- Assistant citations are clickable and focus the cited object.
- Evidence reports contain the question, answer, formulas, papers, links, and build provenance.

## Compatibility And Migration

1. Add PostgreSQL alongside the current JSON repository interface.
2. Import existing `research_*.json` and `seeded_*.json` into stable city IDs.
3. Run contract tests comparing old and new aggregate API payloads.
4. Switch reads to PostgreSQL behind `STORAGE_BACKEND=postgres`.
5. Keep JSON export for reproducibility and demos, but stop using JSON as the live query store.
6. Remove the JSON fallback only after parity, migration, and rollback documentation are verified.

Current building IDs may be preserved as external display IDs while UUIDs become internal keys. Existing frontend URLs and inspectors continue accepting display IDs.

## Error Handling And Observability

- Every job stage emits progress counters and structured events.
- Retries never duplicate papers, edges, or city memberships because writes are idempotent upserts.
- Job heartbeats detect abandoned work and allow safe requeue after a configurable timeout.
- API errors include stable machine codes and user-readable messages.
- Logs include job ID and city ID but never API keys or full prompts containing sensitive user text.
- Metrics cover OpenAlex latency/error rate, papers per minute, embedding throughput, edge count, community duration, retrieval latency, LLM latency, and failed citation validation.

## Security And Data Boundaries

- API keys remain server-side environment variables.
- SQL queries use bound parameters through SQLAlchemy/Psycopg.
- User seed input and questions are length-limited and treated as data, never prompt instructions.
- Groq receives only retrieved evidence needed for one question, not the entire city.
- Exported reports contain OpenAlex metadata and generated analysis, not hidden credentials or raw operational logs.

## Testing Strategy

### Unit Tests

- seed parsing, resolution provenance, dedupe, balanced expansion, scoring, and retry classification;
- candidate edge generation, degree caps, formula versions, citation direction, and deterministic fake embeddings;
- hierarchy, split/merge rules, floors, bridges, streets, temporal trends, and quality metrics;
- retrieval ranking, filter application, evidence packet limits, assistant schema validation, and citation validation;
- repository methods against PostgreSQL, including idempotent upserts and job claiming.

### Integration Tests

- run migrations against an ephemeral PostgreSQL/pgvector database;
- create a city, resolve fake seeds, resume a staged build, and query completed aggregates;
- verify two workers cannot claim the same job;
- verify legacy JSON import and API compatibility;
- verify assistant fallback when Groq is absent and grounded output when Groq is stubbed;
- verify pagination never returns duplicate or missing records.

### Frontend Tests

- seed count, target selection, preview, queueing, progress, cancellation, and completed-city transition;
- aggregate scene loading without paper payloads;
- search/filter/deep-link selection;
- temporal and comparison controls;
- assistant claims and citations focus valid scene objects;
- level-of-detail limits and stable selected-object highlighting.

### Scale Tests

Provide a deterministic synthetic 100,000-paper generator so scale tests do not depend on OpenAlex or Groq.

Required gates on the reference development profile:

- import 100,000 papers without loading the full corpus into the API process;
- produce a bounded sparse graph with no all-pairs operation;
- scene endpoint response contains aggregate objects only and is below 5 MB compressed;
- paper search p95 is below 500 ms after warm-up;
- building-paper pagination p95 is below 500 ms after warm-up;
- assistant retrieval, excluding Groq latency, p95 is below 1 second;
- the frontend never receives more than 2,000 paper nodes for one interior request;
- peak worker memory and total build duration are recorded in the benchmark report rather than assumed.

These are local acceptance targets, not claims about every deployment environment.

### Research Evaluation

- compare Leiden, Louvain, and the current baseline on modularity, conductance, cohesion, and stability;
- compare embedding-based edges with current TF-IDF edges;
- maintain known seed sets with expected domain relationships;
- conduct a user study comparing the city with a conventional 2D graph for topic discovery, relationship explanation, and paper retrieval;
- report task completion time, correctness, cognitive-load rating, and qualitative feedback.

## Delivery Programs And Gates

### Program 1: PostgreSQL Foundation

Deliver database services, migrations, repository interfaces, legacy import, city lifecycle, and PostgreSQL-backed job execution. Gate: current 1,000-paper city loads from PostgreSQL and all existing API/frontend tests still pass.

### Program 2: 100K Graph Pipeline

Deliver durable OpenAlex expansion, embeddings, sparse candidates, hierarchical communities, metrics, temporal aggregates, and a synthetic 100,000-paper benchmark. Gate: the benchmark completes within measured resource bounds and a real smaller OpenAlex build verifies source integration.

### Program 3: Evidence-Grounded Assistant

Deliver hybrid retrieval, broad research intents, structured Groq answers, citations, confidence, and no-LLM fallback. Gate: every generated claim has validated evidence IDs and unsupported IDs are rejected.

### Program 4: Research Workspace

Deliver seed preview/progress, search/filter, hierarchy, temporal views, comparison, exports, and level-of-detail rendering. Gate: Playwright/manual acceptance confirms desktop and mobile workflows without loading all paper records.

## Definition Of Done

The objective is complete only when all of the following are demonstrated:

- PostgreSQL with pgvector is the active storage and retrieval system.
- Existing research and seeded cities are migrated or reproducibly rebuilt.
- A user can submit 20 to 30 seed inputs and request a target of 100,000 papers.
- The build runs asynchronously, survives API restarts, reports progress, and can resume or cancel.
- A seed-only graph is visible before expansion completes.
- A deterministic 100,000-paper benchmark completes and records time, memory, graph size, and quality metrics.
- At least one real OpenAlex seeded build validates the same pipeline at the largest practical count allowed by the configured OpenAlex budget during verification.
- The city exposes districts, buildings, floors, papers, bridges, streets, time, provenance, formulas, and quality metrics.
- Search and filters locate papers without loading the corpus into the browser.
- The assistant answers domain and paper questions, relationship and trend questions, and route questions with clickable validated citations.
- Two cities can be compared and an evidence report can be exported.
- Existing building/bridge/street inspectors and selection behavior remain functional.
- Backend, integration, frontend, build, and scale tests pass.
- `Graph-Cities/Graph_City_Web` has not been modified.

## Explicit Non-Goals

- Rendering all 100,000 papers simultaneously in the main scene.
- Sending the full corpus or full graph to Groq.
- Claiming that LLM self-reported confidence is calibrated confidence.
- Treating layout-only connections as research relationships.
- Replacing OpenAlex as the canonical metadata source in this phase.
- Introducing collaborative accounts, billing, or public multi-tenant authorization before the single-user research workflow is complete.

## External Constraints Confirmed During Design

- OpenAlex documents API authentication, paging, filtering, semantic search, and large-data alternatives including snapshots and changefiles.
- OpenAlex now describes a usage-budget model, so a real 100,000-paper verification run depends on the configured account budget; the deterministic synthetic benchmark is mandatory and does not replace the real-source integration test.
- pgvector supports PostgreSQL 13+, HNSW and IVFFlat indexes, half-precision vectors, hybrid full-text/vector search, and bulk-loading guidance.
- PostgreSQL provides `SKIP LOCKED`, which is suitable for multiple workers claiming independent queued jobs.

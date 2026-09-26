# Original Graph Cities integration

## Objective and authorization

Implement the original Graph Cities method as the default for new research cities, as an application of the original research. Keep the application self-contained inside ResearchGraphCity: installing or running it must not require the sibling Graph-Cities directory or fetching an upstream repository. Preserve the currently working UI, OpenAlex ingestion, asynchronous builds, Groq assistant, Docker PostgreSQL, pgvector retrieval, comparison, timeline, and evidence export.

The user approved implementing the approach discussed in this thread. This written specification records the exact compatibility and fidelity requirements for review before product code changes.

## Source evidence

- Local Graph-Cities and public upstream commit `483c6cbf426511abc86aa950c30b3e8693b6cf6d` contain the Linux x86-64 executables `preproc`, `buffkcore`, and `ewave_next`, but not the C++ `wave-decomposition/src` directory referenced by their Makefile.
- The README's `DanManN/atlas-algorithm` repository URL is unavailable.
- The original Atlas source is available at `https://github.com/fredhohman/atlas-algorithm`, commit `9b805eff7a2d160f366117ee2a754ba1479bb600`. It includes fixed-point edge decomposition, not the complete Graph Cities wave stage.
- Local `graph-strata/lib/graph-algorithms.js` includes fixed-point and wave algorithms. It is supplementary reference material, not automatically proof that its wave variant equals `ewave_next`.
- The existing Graph Cities `wave-decomposition/LICENSE.md` and Atlas license identify MIT terms and different copyright notices. Preserve the applicable original notices for copied material; record origins, revisions, hashes, and modifications.
- The existing `spiral_min.py`, bucket scripts, original street-generation code, bundled outputs, and original executables are the reference for layout and decomposition. Do not silently substitute an unrelated clustering or layout method.

## Algorithm contract

New cities use an explicit versioned algorithm identifier, separate from legacy Leiden cities. The default input is the citation graph, projected to a simple undirected graph. Keep direction, weights, similarity edges, and evidence in PostgreSQL for inspection and research overlays. A citation-plus-similarity configuration is a separate, recorded experimental input; do not silently use it when citation data is absent.

1. Normalize paper IDs to stable integer vertex IDs and sanitize loops and duplicate undirected edges.
2. Apply original iterative fixed-point edge peeling.
3. Split each fixed-point edge layer into its connected components; these are buildings.
4. Apply the original wave/fragment decomposition within the appropriate fixed-point components and preserve its identifiers and internal edge orientation/structure.
5. Derive building/floor/interior geometry from those wave and fragment results, rather than the existing five core bands. Preserve enough metadata to reconstruct and audit the decomposition.
6. Apply original size-bucket ordering, spiral placement, and Delaunay street construction. Geometry-only streets are visibly identified as such and excluded from evidence-grounded research claims.
7. Retain semantic domains as application overlays and evidence-backed bridges as research extensions, with explicit provenance distinguishing them from original geometry.

Isolated papers remain discoverable and visible in an explicitly identified isolate representation; never claim they form a positive-degree fixed point. Do not split a connected fixed point arbitrarily to satisfy mesh or pagination limits. Rendering aggregation must preserve the underlying decomposition and support focused access.

## Self-contained implementation strategy

Bundle available original source and provenance under `backend/vendor/graph_cities/`. Adapt the core behind an application-owned interface; use an equivalent native Python/compiled implementation where necessary for missing stages, with parity against original executable output as a mandatory gate. Native code, if used, must have a reproducible local build, documented toolchain, and no runtime download. Do not ship platform-specific binaries as the only implementation.

Use the original executables in an isolated Linux reference environment to generate test fixtures. Reference generation may use Docker during development; routine app execution must use only files and dependencies supplied by ResearchGraphCity. Keep reference inputs, expected outputs, command lines, source hashes, and equivalence rules in the repository. Missing source is not permission to approximate wave semantics or label a partial implementation complete.

The decomposition interface accepts normalized vertices, undirected edges, and a cancellation callback. It returns edge-layer assignments, connected fixed-point buildings, per-building paper memberships, wave/fragment assignments, bucket/layout metadata, and timings. Deterministic canonical IDs avoid incidental numbering differences in comparisons.

## Database and API compatibility

The original method partitions edges, so one paper can belong to several buildings. Add explicit city/building/paper membership and decomposition edge ownership tables with indexes and uniqueness constraints. Wave/fragment and floor ownership must be scoped to a building. Keep distinct city-paper counts independent of membership counts.

Retain the existing city_papers building/floor fields as a documented primary-location compatibility projection while migrating all membership-sensitive queries to the new tables. Backfill memberships for existing cities through an additive Alembic migration. Existing cities remain readable with their original algorithm metadata; no destructive automatic rebuild or relabeling as original Graph Cities.

Update building paper pagination, floor filters, internal edges, bridge detail, paper lookup, search filtering, timeline aggregates, assistant retrieval, and exported evidence to handle overlapping memberships without duplicate global results. A building's internal edges come from its assigned decomposition, not merely all edges between its member papers. Preserve legacy behavior for legacy cities.

Existing endpoint paths and response fields remain valid. Add algorithm/provenance and multiple-location fields. Existing single-location fields return a deterministic primary location. Assistant evidence can navigate to all valid locations and may not attribute geometric streets to semantic evidence.

## Worker and infrastructure

Keep the current resolve/collect/embed/edges/city/finalize lifecycle, durable jobs, cancellation, retries, and progress reporting. The city stage invokes the original algorithm. Decomposition and persistence check cancellation at bounded points; incomplete output must not mark a city ready. Persist a complete structure transactionally and preserve restart behavior.

Keep Docker's PostgreSQL volume, pgvector extension, existing embeddings and indexes, OpenAlex response cache, and Groq configuration. Preserve the reference-insert batching fix already present in the working tree. Do not print credentials. Tests must use the dedicated research_graph_city_test database, never drop/create the development schema.

## Frontend compatibility

Keep city switching, seed entry and target selection, progress/cancellation, layers, building/bridge/street inspectors, paper selection, floor filtering, interiors, assistant evidence navigation, timeline, comparison, and Markdown export. Extend those interactions for wave/fragment metadata and multiple building memberships. Identify original streets as geometry and semantic bridges as evidence-backed overlays.

The current frontend translates and uniformly scales layout coordinates but does not scale footprints. Preserve original bucket/spiral relative geometry and verify that camera fitting and footprint sizing do not cause overlap. Use aggregate/instanced rendering and bounded focused data access where necessary. A visual grouping cannot erase original building identity. Keep responsive behavior and selected-object highlighting.

## Verification and completion gates

- Original-output parity for fixed-point edge layers, connected components, waves/fragments, and bucket/layout ordering on hand-checkable graphs and deterministic random graphs. Compare partitions up to canonical relabeling and document any coordinate tolerance.
- Explicit cases: empty graph, isolates, one edge, paths, cycles, stars, cliques, disconnected components, shared vertices across layers, duplicate/reversed edges, and cancellation.
- Database migration upgrade against a disposable copy of legacy data; legacy API parity and correct multiple memberships, edge ownership, floor filters, cursors, and distinct counts.
- End-to-end worker build with deterministic OpenAlex data, including citation-free input and reference-heavy batches; restart/cancel tests and correct algorithm provenance.
- Full backend suite in JSON and PostgreSQL modes, frontend suite, and frontend production build. Preserve actual behaviors rather than weakening tests to accommodate regressions.
- Runtime smoke checks through the frontend proxy for city detail, focused interiors, assistant retrieval, timeline, comparison, and export; browser verification of the changed interactions.
- Groq request/response contracts and evidence validation tested with controlled responses, plus configured live availability reported separately. Do not claim live model availability from a key's presence.
- Repeat the synthetic 100,000-paper benchmark for this algorithm and record actual time, memory, graph/building counts, compressed scene size, and retrieval latency. Previous Leiden timing is not evidence for the new algorithm.
- Verify a clean standalone checkout without the sibling Graph-Cities directory can install, migrate, build a city, and run tests using documented dependencies.
- Existing development cities and credentials remain intact; API and worker run the verified code after migrations are applied safely.

## Current status

Implementation and verification are recorded in `docs/research/original-graph-cities-reference/verification.md`. Original decomposition, persistence, worker, geometry and UI integration are implemented; development migrations are applied and legacy cities preserved. This section supersedes the initial pre-implementation status.

See `docs/research/original-graph-cities-reference/compatibility-baseline.md` for the executed baseline and specific membership, assistant, street, and rendering compatibility risks.

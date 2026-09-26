# Original Graph Cities integration verification

Verified locally on 2026-09-26. New PostgreSQL worker builds use `graph-cities-v1`; legacy cities keep their previous algorithm. The application is self-contained and does not load code or binaries from the sibling Graph-Cities directory.

## Fidelity and compatibility evidence

| Requirement | Implementation and verification |
| --- | --- |
| Original fixed-point edge peeling, waves and fragments | `app/pipeline/fixed_points.py`; 31 original-executable fixtures cover hand graphs and deterministic random graphs. Tests compare edge layers, wave/fragment partitions, components and shared vertices. Source revisions, licenses and binary hashes are retained under `backend/vendor/graph_cities` and the fixtures. |
| Original geometry | `original_layout.py` follows bucket thresholds, spiral placement, wave-map counts and frustum formulas. Numeric fixtures evaluate the original scripts. Wave target counts include later fragments in the same wave. Tiny bucket bases and degenerate Voronoi cases have documented fallbacks. |
| Original building identity | Connected fixed points remain intact, including the 100k benchmark's single building with 50,000 waves. Every wave and owned edge is stored; scene sampling only changes the overview. |
| Shared paper membership | Explicit building/floor membership and decomposition-edge tables; repository tests cover secondary locations, owned edges, floor filters, cursors, search and distinct timeline counts. |
| Existing cities and database | Additive migrations 0009–0011, populated legacy migration/backfill tests and primary-location compatibility fields. Development DB is at `20260925_0011`; all four pre-existing cities match their pre-migration status, paper/building counts and algorithm metadata. Backup taken before migration. |
| Worker and cancellation | Real worker/pipeline test with deterministic OpenAlex input, durable job and stale-job tests, transactional rebuild/rollback tests, cancellation before work and during persistence. Cancellation polling is throttled with a fresh final check. |
| Large reference inserts | Existing batching fix retained; regression inserts 108,000 references without exceeding PostgreSQL's parameter limit. |
| Existing application features | OpenAlex ingestion, embeddings, pgvector retrieval, Groq assistant, semantic districts, evidence bridges, timeline, comparison and export remain integrated. Geometric streets are explicitly excluded from research evidence. |
| Bounded UI with focused access | At most 64 wave samples per building in city overview; all wave floors are paged. Paper pages show 50 records, internal-edge pages 80, with lookahead. Later paper selection supplies its full record and keeps the interior at most 200 records. Edge cursors include type so citation/similarity pairs are not skipped at boundaries; old cursors still work. |
| Existing JSON mode | Read-only compatibility retained; floor, paper and edge pagination supported, including static research endpoint aliases. |

## Executed checks

- Working tree backend: **213 tests passed** with the dedicated `research_graph_city_test` database.
- Standalone copy outside this workspace, without sibling Graph-Cities: dependencies installed in a fresh Python environment and with `npm ci`; refreshed final source passed **213 backend tests in JSON mode and 213 in PostgreSQL mode**, plus **45 frontend tests and production build**.
- Development Docker PostgreSQL is healthy; pgvector extension version `0.8.6` is installed. API, worker and frontend run locally. No credentials were changed or included in reports.
- Browser checks: existing research city, original 300-paper city, complete tower camera fit, floor page 2 / wave 101, entering/exiting an interior, paper page 5 / selection beyond the initial 200, and internal-edge paging. Browser errors are checked by the harness.
- Through the frontend proxy: timeline, comparison and Markdown evidence export returned HTTP 200. A live Groq-backed assistant query returned HTTP 200, `model_available: true`, and three paper results.
- Independent integration review resolved the paper-access and edge-cursor findings; no remaining concrete blockers were identified in the reviewed changes.
- Known verification warnings: existing Vite bundle-size warning and a dependency deprecation warning in the fresh Python installation. Neither prevents tests or build.

Tests establish reference parity for the recorded cases, not a mathematical proof for every possible graph. Semantic districts and research assistance are application extensions, not claimed as original paper algorithms.

## 100,000-paper measurement

See [final raw report](benchmark-100k-final.json). Synthetic local input contains 100,000 papers, 99,999 citations, and 1,236,852 similarity edges. Default decomposition uses citations; similarity remains an evidence/retrieval overlay.

| Measurement | Result |
| --- | ---: |
| Total local compute | 102.979 seconds |
| Persist / embed / edges / city | 9.104 / 17.555 / 42.969 / 33.351 seconds |
| Buildings / waves | 1 / 50,000 |
| Peak process RSS | 2,683,813,888 bytes |
| Scene JSON / gzip | 44,730 / 4,806 bytes |
| Paper search p95 | 86.517 ms |
| Assistant retrieval p95 | 148.663 ms |
| Building papers p95 | 55.090 ms |

The database was migrated with Alembic, including its vector indexes. This is synthetic local processing, excludes OpenAlex collection and remote LLM latency, and is not a guarantee for every 100k graph. Graph density and overlapping memberships affect cost. A connected graph can legitimately produce one building. OpenAlex availability and reachable records can produce fewer papers than the requested target.

The [initial run](benchmark-100k-initial.json) took 180.097 seconds and exposed slow queries on freshly bulk-loaded tables. The integration adds statistics refresh and missing relationship/cascade indexes. Retained-city query p95 improved from 1906.281 ms to 82.523 ms; the final cold run above reached 55.090 ms. Cold embedding timings varied, so the entire timing improvement is not attributed to the index changes.

## Try it in the UI

Use the commands in [PostgreSQL development](../../postgresql-development.md). Docker runs PostgreSQL/pgvector; the API, worker and Vite frontend run in separate terminals. Open `http://127.0.0.1:5173`.

1. Existing Research City and Seeded City buttons still open legacy data.
2. Enter up to 30 unique paper titles, DOIs or OpenAlex URLs (one per line), choose a target such as 100,000 and select **Build Seeded City**. The worker performs collection, embedding, edge construction and the original city stage.
3. On completion, select a building. Inspect its original fixed-point description, semantic district and labels. Browse floors, papers and internal edges using the page controls.
4. Enter the building for its bounded interior preview; selecting a paper from a later inspector page makes that paper available to the focused view. Multiple-location buttons navigate to other fixed points containing the paper.
5. Ask the research assistant, inspect its cited papers, apply year/open-access filters, view the timeline, compare cities and export evidence. Geometric streets are distinguished from evidence-backed relationships.

Changing the target does not alter already built cities. No legacy city is silently rebuilt or relabeled.

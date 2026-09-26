# Original Graph Cities implementation plan

> Execute inline using superpowers:executing-plans. User authorization is the instruction to implement and continue; do not repeat permission gates for this scope.

**Goal:** Self-contained original Graph Cities decomposition, structure and layout with all existing research application features preserved.
**Architecture:** Add a versioned fixed-point/wave engine with original-output parity fixtures; persist overlapping memberships and explicit edge ownership; adapt existing repositories and renderer through additive fields and legacy fallbacks.
**Tech stack:** Python, igraph, NumPy/SciPy, FastAPI, SQLAlchemy, PostgreSQL/pgvector, React/Three.js; original executables are development reference oracles only.
**Spec:** `docs/superpowers/specs/2026-09-24-original-graph-cities-design.md`.

## Constraints and review focus

- No sibling-directory or upstream-network dependency at runtime. Bundle provenance, applicable licenses and source references.
- Preserve existing legacy cities; never apply destructive tests to the development database.
- Shared vertices must appear in every building without multiplying global counts.
- Internal edges must follow decomposition ownership, not an induced-subgraph shortcut.
- Geometric streets must never become semantic evidence in either assistant path.
- Isolates, missing citations, degenerate layouts and large single fixed points must remain usable.
- Cancellation and rebuild must not publish partial structures or lose the reference batching fix.

## Task 1: Original-output verified algorithm engine

Files: `backend/app/pipeline/fixed_points.py`, `backend/tests/test_fixed_points.py`, `backend/tests/fixtures/graph_cities/`, `backend/vendor/graph_cities/`, `backend/scripts/generate_graph_cities_reference.py`.

Interface: `decompose_graph(node_ids, edges, cancel_check=None)` returns canonical edges with fixed-point, building, wave and fragment IDs; buildings include their complete memberships, wave/fragment metadata and isolates are explicitly separate.

- [x] Generate oracle fixtures with original preproc/buffkcore/ewave_next, including hand graphs and seeded random graphs; record binary hashes and command provenance.
- [x] Write failing parity tests, overlapping-membership test, input sanitation and cancellation tests. Run `pytest tests/test_fixed_points.py -q` and inspect RED.
- [x] Implement repeated maximum-core edge peeling and original wave/fragment behavior, checking every output against the oracle. Connected components are computed independently in each edge layer.
- [x] Run parity and property tests; optimize using igraph/arrays without changing partitions. Commit engine, fixtures and provenance.

## Task 2: Additive persistence and legacy compatibility

Files: `backend/app/models.py`, `backend/alembic/versions/20260924_0009_graph_city_memberships.py`, `backend/app/repositories/postgres_city.py`, `backend/tests/test_repositories.py`, `backend/tests/test_hierarchical_city.py`.

- [x] Add failing tests for one paper in two buildings, owned internal edges, floor filters, cursor pagination, search filters and distinct timeline counts.
- [x] Add membership and decomposition-edge tables with city-scoped indexes/constraints and additive metadata. Backfill legacy memberships in migration; retain old primary fields for clients.
- [x] Update repository queries to explicit memberships for new cities, retaining legacy fallback. Return multiple locations plus deterministic primary location.
- [x] Verify migration on a disposable copy of legacy data and run repository/API suites. Commit.

## Task 3: Structure, layout and pipeline

Files: `backend/app/pipeline/original_city.py`, `backend/app/pipeline/original_layout.py`, `backend/app/pipeline/build.py`, `backend/app/pipeline/city_structure.py`, `backend/tests/test_original_city.py`, `backend/tests/test_build_pipeline.py`.

- [x] Add RED tests for worker default algorithm, citation projection, isolates, transactional rebuild and cancellation.
- [x] Persist fixed-point buildings and wave/fragment floors without arbitrary splitting. Preserve metrics, labels, domains and existing semantic bridges as extensions.
- [x] Implement original size bucket/spiral ordering and Voronoi-ridge/Delaunay adjacency with fixture comparisons. Mark geometry-only streets explicitly.
- [x] Make new worker builds use this versioned structure; keep embeddings, edge construction, caches and all existing lifecycle stages. Run worker/integration tests; commit.

## Task 4: Assistant and UI

Files: `backend/app/assistant.py`, `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/types.ts`, `frontend/src/CityScene.tsx`, `frontend/src/Inspector.tsx`, `frontend/src/store.ts`, `frontend/src/sceneLayout.ts`, corresponding tests.

- [x] Add RED tests for multiple-location navigation, geometry excluded from claims, floor/interior selection, legacy cities and preserved layout proportions.
- [x] Extend API schemas and assistant packets without breaking existing fields; distinguish original streets from research relationships in UI and both LLM paths.
- [x] Show algorithm/wave/fragment provenance and support all memberships; preserve existing controls, selection, filters, comparison, timeline and export.
- [x] Run frontend tests/build, assistant/API tests and browser smoke checks. Commit.

## Task 5: Scale, standalone runtime and final review

Files: `backend/scripts/benchmark_100k.py`, `README.md`, `docs/100k-operations.md`, `docs/postgresql-development.md`.

- [x] Run full backend suites with explicit test database, frontend tests/build and 100k original-algorithm benchmark; record actual timing/memory/payload/retrieval gates.
- [x] Verify standalone install/run without Graph-Cities directory and preserve pinned notices/dependencies.
- [x] Review whole change against spec with fresh reviewer, resolve correctness findings with regressions.
- [x] Apply additive migration safely, restart local API/worker with verified code, smoke-test all existing application paths, and report actual LLM availability separately.

## Execution ledger

- Baseline: 120 backend / 34 frontend tests pass; production frontend build passes (existing large-chunk warning).
- Ruling: work on `feature/original-graph-cities` in the current checkout to retain the user's running setup and uncommitted verified reference-insert fix. Existing worker has no hot reload, so new engine does not change a running job until restart.
- Ruling: execute under user's repeated implementation/continuation authorization instead of adding further skill approval gates. The documented preservation and fidelity constraints remain binding.
- Task 1 core implemented: `fixed_points.py`, 31 original executable fixtures, 35 tests (including canonical wave partitions, shared vertices, sanitation, cancellation, vertex wave geometry). A 100,000-vertex path completes the engine in 0.289 seconds and yields one building / 50,000 waves; this is not an end-to-end benchmark. Degree buckets avoid quadratic scans across long chains.
- Task 2 foundation implemented: additive migration 0009, explicit building/floor paper memberships and canonical decomposition ownership; repository methods use these for graph-cities-versioned cities and retain legacy queries otherwise. Tests cover secondary membership, edge ownership, pagination, search and distinct timeline counts. Full backend suite passed 157 tests before the additional vertex-geometry test (35th engine test).
- Remaining: legacy-data migration/backfill verification, layout/frustum oracle fixtures, original city persistence, worker default switch, assistant and frontend integration, full scale and standalone/runtime checks. No development-database migration or worker algorithm switch has occurred.
- Ruling: the original engine can produce 50,000 waves in a single building. Preserve every wave and edge assignment in the database; scene rendering must use a bounded geometric representation plus paged focused floors, rather than splitting the original fixed point or shipping all floor meshes.
- Geometry implementation: original script numeric fixtures now verify bucket thresholds, spiral coordinates/rotation/radius, and frustum heights. Added original Voronoi street adjacency with documented tiny/degenerate fallbacks, plus wave profiles retaining source/target overlap and fragments. Engine/layout focused suite: 48 passed; full backend suite: 171 passed in 10.45 seconds against the dedicated test database.
- Migration verification: a populated disposable legacy schema survives 0008 -> 0009 with unchanged city metadata and primary locations; both membership tables are backfilled and legacy queries still work. Four membership tests pass. The development database remains untouched.
- Next integration work: persist original buildings/waves/profiles and all overlapping memberships, switch worker only with integration coverage, then adapt bounded scene/focused floor access and assistant navigation. Full UI, scale, standalone, and runtime gates remain outstanding.
- Original persistence and worker integration implemented: `original_city.py` stores deterministic buildings, full wave floors, shared building/floor memberships, and edge ownership with COPY in one transaction. Rebuild and interrupted-persistence rollback tests pass. Citation-only input is default; explicit hybrid input is recorded; isolates have a labeled representation. Semantic districts and research relationships remain overlays, geometric streets have their own type and no evidence score. The worker now calls this pipeline; the local running worker has not yet been restarted.
- Added migration 0010 to widen floor indices from SMALLINT to INTEGER after reproducing a failure at wave 50,000. Populated migration upgrade/downgrade tests pass against the disposable database. No development migrations applied yet.
- Assistant packets include secondary locations; geometry streets are excluded from retrieval evidence and legacy navigation prompts. Scene floors are sampled to at most 64 per original building; the new `/building/{id}/floors` endpoint pages all waves. Interior node placement now uses explicit floor memberships and compact display levels while preserving real wave indices.
- Verification: full backend suite 178 passed in 12.83s; frontend 35 passed and production build passed (existing chunk-size warning). Remaining frontend work includes original frustum rendering, proportional scene normalization, paginated floor controls, multiple-location navigation, and provenance labels. Assistant prompt size bounds, scale/standalone/browser/runtime verification and final review remain outstanding.
- Frontend integration added: stored original frustums render with uniform scene scaling; sampled wave gaps interpolate only the preview. Inspector pages all floors (with direct page input), identifies original/isolated buildings and geometric streets, and navigates secondary paper memberships. All 41 frontend tests and production build pass. Assistant prompt projection caps membership expansion while preserving full API data.
- First 100k original benchmark completed building and queries: 100,000 papers, 99,999 citation edges, 1,235,679 similarity edges, one fixed point, 50,000 waves. Compute stages 180.097s, city 31.460s, peak RSS 2,419,507,200 bytes, compressed scene 4,809 bytes. This does not meet the prior <120s local-compute target; embedding alone took 91.168s. Initial pagination p95 1906.281ms exposed missing fresh-table statistics. Raw report saved under `docs/research/original-graph-cities-reference/benchmark-100k-initial.json`.
- Scale fixes: migration 0011 indexes floor/building references and membership cascade targets; new-city persistence ANALYZEs bulk-loaded tables. The retained 100k city rebuilt in 40.107s, pagination p95 fell to 82.523ms, and full synthetic cleanup finished in 11.516s. Initial cleanup was deliberately cancelled after observing repeated unindexed floor SET NULL work; all synthetic data has now been cleaned. No running benchmark handles remain.
- Remaining: investigate cold embedding time and rerun final benchmark, browser smoke tests, standalone install verification, development migration/service startup, final fresh review. Playwright installed outside the repo at `/tmp/researchgraphcity-browser` for browser verification; Chrome is available. Development DB still untouched. Full backend suite after scale fixes: 180 passed in 15.10s. No running test/benchmark handles remain. The full benchmark used Alembic-created HNSW indexes; ORM `create_all` does not declare these indexes, so compare prior timings cautiously.

## Verification update — 2026-09-26

This update supersedes historical in-progress notes above. Development migrations 0009–0011 are applied; all four original cities remain unchanged in status/counts/algorithm metadata. API, worker, frontend and Docker PostgreSQL/pgvector are running. Live Groq query, timeline, comparison and export pass through the frontend proxy.

The final synthetic 100k run completed in 102.979 seconds, with 50,000 full waves in one building, peak RSS 2.68 GB, scene gzip 4,806 bytes, and paper-page p95 55.090 ms. Raw initial and final reports are retained. Wave-map oracle checks corrected targets to include later fragments within the same wave; cancellation polling is bounded with a fresh precommit check.

Independent review findings are resolved: inspector paper/edge cursors now reach beyond initial batches, later paper records populate focused selection, and edge-type tie-breakers prevent skipping citation/similarity pairs. Working-tree backend has 213 passing tests; refreshed standalone copy passes 213 in each storage mode and 45 frontend tests plus production build. Browser paper-page selection has no JavaScript errors. See `docs/research/original-graph-cities-reference/verification.md` for the requirement/evidence matrix, runtime checks, limitations and UI steps.

Final UI provenance check: selected floors expose original wave IDs, fragment vertex counts and internal/boundary edge counts. Legacy floors retain their existing presentation. All task checklists above are complete; local commits preserve the work on `feature/original-graph-cities` without publishing or merging.

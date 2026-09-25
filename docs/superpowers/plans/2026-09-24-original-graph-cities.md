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

- [ ] Generate oracle fixtures with original preproc/buffkcore/ewave_next, including hand graphs and seeded random graphs; record binary hashes and command provenance.
- [ ] Write failing parity tests, overlapping-membership test, input sanitation and cancellation tests. Run `pytest tests/test_fixed_points.py -q` and inspect RED.
- [ ] Implement repeated maximum-core edge peeling and original wave/fragment behavior, checking every output against the oracle. Connected components are computed independently in each edge layer.
- [ ] Run parity and property tests; optimize using igraph/arrays without changing partitions. Commit engine, fixtures and provenance.

## Task 2: Additive persistence and legacy compatibility

Files: `backend/app/models.py`, `backend/alembic/versions/20260924_0009_graph_city_memberships.py`, `backend/app/repositories/postgres_city.py`, `backend/tests/test_repositories.py`, `backend/tests/test_hierarchical_city.py`.

- [ ] Add failing tests for one paper in two buildings, owned internal edges, floor filters, cursor pagination, search filters and distinct timeline counts.
- [ ] Add membership and decomposition-edge tables with city-scoped indexes/constraints and additive metadata. Backfill legacy memberships in migration; retain old primary fields for clients.
- [ ] Update repository queries to explicit memberships for new cities, retaining legacy fallback. Return multiple locations plus deterministic primary location.
- [ ] Verify migration on a disposable copy of legacy data and run repository/API suites. Commit.

## Task 3: Structure, layout and pipeline

Files: `backend/app/pipeline/original_city.py`, `backend/app/pipeline/original_layout.py`, `backend/app/pipeline/build.py`, `backend/app/pipeline/city_structure.py`, `backend/tests/test_original_city.py`, `backend/tests/test_build_pipeline.py`.

- [ ] Add RED tests for worker default algorithm, citation projection, isolates, transactional rebuild and cancellation.
- [ ] Persist fixed-point buildings and wave/fragment floors without arbitrary splitting. Preserve metrics, labels, domains and existing semantic bridges as extensions.
- [ ] Implement original size bucket/spiral ordering and Voronoi-ridge/Delaunay adjacency with fixture comparisons. Mark geometry-only streets explicitly.
- [ ] Make new worker builds use this versioned structure; keep embeddings, edge construction, caches and all existing lifecycle stages. Run worker/integration tests; commit.

## Task 4: Assistant and UI

Files: `backend/app/assistant.py`, `backend/app/main.py`, `backend/app/schemas.py`, `frontend/src/types.ts`, `frontend/src/CityScene.tsx`, `frontend/src/Inspector.tsx`, `frontend/src/store.ts`, `frontend/src/sceneLayout.ts`, corresponding tests.

- [ ] Add RED tests for multiple-location navigation, geometry excluded from claims, floor/interior selection, legacy cities and preserved layout proportions.
- [ ] Extend API schemas and assistant packets without breaking existing fields; distinguish original streets from research relationships in UI and both LLM paths.
- [ ] Show algorithm/wave/fragment provenance and support all memberships; preserve existing controls, selection, filters, comparison, timeline and export.
- [ ] Run frontend tests/build, assistant/API tests and browser smoke checks. Commit.

## Task 5: Scale, standalone runtime and final review

Files: `backend/scripts/benchmark_100k.py`, `README.md`, `docs/100k-operations.md`, `docs/postgresql-development.md`.

- [ ] Run full backend suites with explicit test database, frontend tests/build and 100k original-algorithm benchmark; record actual timing/memory/payload/retrieval gates.
- [ ] Verify standalone install/run without Graph-Cities directory and preserve pinned notices/dependencies.
- [ ] Review whole change against spec with fresh reviewer, resolve correctness findings with regressions.
- [ ] Apply additive migration safely, restart local API/worker with verified code, smoke-test all existing application paths, and report actual LLM availability separately.

## Execution ledger

- Baseline: 120 backend / 34 frontend tests pass; production frontend build passes (existing large-chunk warning).
- Ruling: work on `feature/original-graph-cities` in the current checkout to retain the user's running setup and uncommitted verified reference-insert fix. Existing worker has no hot reload, so new engine does not change a running job until restart.
- Ruling: execute under user's repeated implementation/continuation authorization instead of adding further skill approval gates. The documented preservation and fidelity constraints remain binding.
- Task 1 core implemented: `fixed_points.py`, 31 original executable fixtures, 35 tests (including canonical wave partitions, shared vertices, sanitation, cancellation, vertex wave geometry). A 100,000-vertex path completes the engine in 0.289 seconds and yields one building / 50,000 waves; this is not an end-to-end benchmark. Degree buckets avoid quadratic scans across long chains.
- Task 2 foundation implemented: additive migration 0009, explicit building/floor paper memberships and canonical decomposition ownership; repository methods use these for graph-cities-versioned cities and retain legacy queries otherwise. Tests cover secondary membership, edge ownership, pagination, search and distinct timeline counts. Full backend suite passed 157 tests before the additional vertex-geometry test (35th engine test).
- Remaining: legacy-data migration/backfill verification, layout/frustum oracle fixtures, original city persistence, worker default switch, assistant and frontend integration, full scale and standalone/runtime checks. No development-database migration or worker algorithm switch has occurred.
- Ruling: the original engine can produce 50,000 waves in a single building. Preserve every wave and edge assignment in the database; scene rendering must use a bounded geometric representation plus paged focused floors, rather than splitting the original fixed point or shipping all floor meshes.

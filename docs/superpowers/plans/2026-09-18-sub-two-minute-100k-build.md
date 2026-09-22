# Sub-Two-Minute 100K Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the current graph semantics while reducing the local 100,000-paper compute pipeline below 120 seconds.

**Architecture:** Replace per-paper SQL vector probes with a city-scoped parallel HNSW pass and PostgreSQL bulk staging, cache reusable neighbors globally, parallelize/snapshot-enable collection, overlap expansion with embeddings, and bulk-persist city assignments. PostgreSQL remains authoritative and the public API remains compatible.

**Tech Stack:** Python 3.13, hnswlib, NumPy, psycopg 3 COPY, SQLAlchemy 2, PostgreSQL 16, pgvector, igraph/Leiden, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-sub-two-minute-100k-build-design.md`

## Global Constraints

- Keep `semantic_k=20`; optimization must not lower graph quality by reducing neighbors.
- The 100K compute benchmark must finish in less than 120 seconds on the baseline machine.
- Preserve citations, topic/attribute evidence, degree cap 40, hierarchy, and all API response contracts.
- OpenAlex network time is reported separately and never represented as deterministic.
- Do not modify `Graph-Cities/Graph_City_Web`.
- This workspace has no Git repository at `ResearchGraphCity/`; track changes through plan checkboxes and verification output rather than commits.

---

### Task 1: Performance schema and configuration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/20260918_0004_fast_build.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces `PaperNeighborRecord` keyed by `(model, algorithm_version, source_openalex_id, rank)`.
- Produces settings `graph_workers`, `openalex_workers`, `openalex_min_interval_seconds`, and `openalex_snapshot_path`.

- [x] Add failing configuration and model metadata tests.
- [x] Run targeted tests and confirm the new fields are absent.
- [x] Add the neighbor-cache table, indexes, migration, validated settings, and environment examples.
- [x] Run migration/config tests and confirm they pass.

### Task 2: City-scoped HNSW and bulk edge merge

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/pipeline/vector_neighbors.py`
- Modify: `backend/app/pipeline/edges.py`
- Test: `backend/tests/test_vector_neighbors.py`
- Modify: `backend/tests/test_sparse_edges.py`

**Interfaces:**
- Produces `compute_city_neighbors(city_id, repository, model, top_k, workers, cancel_check) -> NeighborBuildResult`.
- Produces bulk semantic edge merge preserving canonical undirected pairs and cache rows.

- [x] Add failing tests for deterministic canonical top-20 neighbors, cancellation, cache reuse, and maximum degree.
- [x] Run tests and confirm the HNSW interface is missing.
- [x] Add hnswlib and implement a per-city index with batched parallel querying.
- [x] Add psycopg COPY staging for cache and semantic-edge merges.
- [x] Replace `_insert_semantic_neighbors` while preserving its count contract.
- [x] Run vector and sparse-edge tests.

### Task 3: Fast embedding and paper persistence

**Files:**
- Create: `backend/app/pipeline/bulk_io.py`
- Modify: `backend/app/pipeline/embeddings.py`
- Modify: `backend/scripts/benchmark_100k.py`
- Test: `backend/tests/test_bulk_pipeline.py`

**Interfaces:**
- Produces `copy_rows(connection, table, columns, rows)` and staging-table merge helpers.
- `embed_city_papers` retains its signature and returns the inserted count.

- [x] Add failing tests for idempotent bulk embeddings and exact vector values.
- [x] Run tests and confirm the bulk path is absent.
- [x] Implement psycopg COPY staging and set-wise embedding merge.
- [x] Convert deterministic benchmark paper/reference loading to the production bulk helper.
- [x] Run bulk and embedding tests.

### Task 4: Parallel and snapshot-backed OpenAlex expansion

**Files:**
- Modify: `backend/app/openalex_client.py`
- Create: `backend/app/openalex_snapshot.py`
- Modify: `backend/app/pipeline/expansion.py`
- Modify: `backend/app/pipeline/build.py`
- Test: `backend/tests/test_openalex_client.py`
- Test: `backend/tests/test_expansion.py`
- Create: `backend/tests/test_openalex_snapshot.py`

**Interfaces:**
- Produces `parallel_round_robin(iterables, max_workers, cancel_check)` with bounded outstanding work.
- Produces `OpenAlexSnapshot.iter_candidates(seed_papers, limit)` from JSONL metadata.
- Expansion accepts worker count, optional snapshot, and an `on_batch_committed` callback.

- [x] Add failing tests for bounded parallel streams, cancellation, deterministic dedupe, and snapshot lookup.
- [x] Run tests and confirm the new interfaces are absent.
- [x] Implement thread-local HTTP sessions and bounded parallel collection with shared retry/cache behavior.
- [x] Implement indexed JSONL snapshot iteration.
- [x] Wire snapshot preference and batch callbacks into expansion/build.
- [x] Run OpenAlex and expansion tests.

### Task 5: Overlap collection and embedding

**Files:**
- Modify: `backend/app/pipeline/build.py`
- Modify: `backend/app/pipeline/expansion.py`
- Test: `backend/tests/test_pipeline_build.py`

**Interfaces:**
- Expansion callback receives `(city_id, committed_openalex_ids)` after each transaction.
- Build owns a single background embedding executor and performs a final idempotent catch-up pass.

- [x] Add a failing orchestration test proving embedding starts before expansion completes.
- [x] Run the test and confirm stages are serial.
- [x] Add bounded background embedding scheduling and error propagation.
- [x] Preserve progress, cancellation, and restart semantics.
- [x] Run orchestration and lifecycle tests.

### Task 6: Bulk city-structure persistence

**Files:**
- Create: `backend/app/pipeline/structure_persistence.py`
- Modify: `backend/app/pipeline/city_structure.py`
- Test: `backend/tests/test_hierarchical_city.py`
- Create: `backend/tests/test_structure_persistence.py`

**Interfaces:**
- Produces `persist_city_structure(city_id, repository, prepared, assignments, edge_rows, seed) -> dict[str, int]`.
- Uses one assignment staging merge for building/floor IDs.

- [x] Add failing parity tests comparing hierarchy metrics, assignments, floors, and relationships.
- [x] Run tests and confirm the bulk persistence interface is absent.
- [x] Pre-generate UUIDs and bulk-insert aggregate entities.
- [x] COPY paper assignments into a temporary table and update memberships set-wise.
- [x] Bulk-insert relationship evidence and finalize city/run records.
- [x] Run hierarchy and persistence tests.

### Task 7: Benchmark, tune, and acceptance

**Files:**
- Modify: `backend/scripts/benchmark_100k.py`
- Modify: `docs/100k-operations.md`
- Modify: `docs/superpowers/plans/2026-09-18-sub-two-minute-100k-build.md`

**Interfaces:**
- Benchmark emits collection time, compute time, cache hit count, stage timings, quality counts, peak RSS, and payload/latency metrics.

- [x] Run a 10K benchmark and profile any stage exceeding its proportional budget.
- [x] Run the cold 100K benchmark with `semantic_k=20`; require compute total under 120 seconds.
- [x] Run a warm-cache benchmark and verify reuse.
- [x] Verify edge quality, max degree, hierarchy, gzip scene size, and p95 retrieval gates.
- [x] Run all backend tests in JSON and PostgreSQL modes.
- [x] Run frontend tests and production build.
- [x] Verify live API/frontend/worker and confirm `Graph_Cities_Web` is untouched.
- [x] Record measurements and mark this plan complete only when every gate passes.

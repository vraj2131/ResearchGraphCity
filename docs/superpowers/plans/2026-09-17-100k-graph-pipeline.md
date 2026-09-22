# 100K Graph Pipeline Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with tests and verification at each checkpoint.

**Goal:** Turn a queued city containing 1–30 user seed papers into a resumable, evidence-backed PostgreSQL graph city containing up to 100,000 related papers without all-pairs graph construction or unbounded API responses.

**Architecture:** A standalone worker resolves seeds, persists a seed preview, expands a balanced OpenAlex frontier, embeds papers in fixed 64-dimensional space, creates bounded edge candidates, detects hierarchical communities, and stores aggregate scene geometry. Each stage is idempotent and updates the existing job row.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL 16, pgvector, OpenAlex API, scikit-learn hashing embeddings, igraph/Leiden where available, NetworkX fallback for small graphs.

---

### Task 1: Resilient OpenAlex Client And Cache

**Files:**
- Create: `backend/app/openalex_client.py`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_openalex_client.py`

- [x] Resolve title, DOI, and OpenAlex IDs with explicit match provenance.
- [x] Add cursor pagination, request fingerprints, PostgreSQL response cache, bounded retries, and `Retry-After` handling.
- [x] Add batched fetch-by-ID and citing-work/reference expansion methods.
- [x] Verify retry, cache, pagination, malformed response, and cancellation behavior.

### Task 2: Idempotent Paper Persistence And Seed Preview

**Files:**
- Create: `backend/app/pipeline/persistence.py`
- Create: `backend/app/pipeline/seed_stage.py`
- Create: `backend/app/routes/seed_graph.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_seed_stage.py`

- [x] Upsert normalized papers, references, memberships, and seed provenance in bounded transactions.
- [x] Build and expose `/api/cities/{city_id}/seed-graph` immediately after seed resolution.
- [x] Preserve unresolved warnings without failing when one or more seeds resolve.
- [x] Verify rerunning the stage creates no duplicate records.

### Task 3: Balanced Expansion To Target

**Files:**
- Create: `backend/app/pipeline/expansion.py`
- Test: `backend/tests/test_expansion.py`

- [x] Score candidates using semantic-to-seed, citation proximity, topic overlap, source quality, and recency.
- [x] Apply per-seed and per-domain soft quotas with redistribution.
- [x] Persist each page and frontier checkpoint before the next request.
- [x] Stop at the target, source exhaustion, or cooperative cancellation.

### Task 4: Fixed Embeddings And Bounded Sparse Edges

**Files:**
- Create: migration `backend/alembic/versions/20260917_0002_vector_indexes.py`
- Create: `backend/app/pipeline/embeddings.py`
- Create: `backend/app/pipeline/edges.py`
- Test: `backend/tests/test_sparse_edges.py`

- [x] Use deterministic 64-dimensional hashing embeddings and pgvector indexes.
- [x] Generate candidates from citations, top-20 semantic neighbors, top-10 specific-topic peers, and capped exact overlaps.
- [x] Retain at most 40 non-citation similarity edges per paper while retaining citation edges separately.
- [x] Verify candidate count grows linearly and no all-pairs function is called.

### Task 5: Hierarchical City Construction

**Files:**
- Create: `backend/app/pipeline/communities.py`
- Create: `backend/app/pipeline/city_structure.py`
- Test: `backend/tests/test_hierarchical_city.py`

- [x] Detect reproducible paper communities, split oversized groups, and preserve valid tiny outskirts.
- [x] Map paper communities to buildings and core/time bands to 1–5 floors.
- [x] Group buildings into semantic districts without repeated generic domain labels.
- [x] Generate bridges and nonzero research streets with representative cross-paper evidence.

### Task 6: Production Worker Handler

**Files:**
- Create: `backend/app/pipeline/build.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/jobs.py`
- Test: `backend/tests/test_build_pipeline.py`

- [x] Register the real staged handler in the worker CLI.
- [x] Update city status/counts, stage progress, warnings, and failure provenance.
- [x] Make completed stages restart-safe and cancellation cooperative.
- [x] Verify API submission returns before ingestion and a worker completes a deterministic fake-source build.

### Task 7: Bounded Scene And Detail APIs

**Files:**
- Modify: `backend/app/repositories/postgres_city.py`
- Create: `backend/app/routes/scene.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_scale_api.py`

- [x] Add `/api/cities/{city_id}/scene` for aggregate-only data.
- [x] Remove unbounded paper membership arrays from the main PostgreSQL scene.
- [x] Add cursor paging with a hard maximum of 200 for papers and edges.
- [x] Verify scene response size is independent of paper count within an aggregate layout.

### Task 8: Scale Benchmark And Operational Verification

**Files:**
- Create: `backend/scripts/benchmark_100k.py`
- Create: `docs/100k-operations.md`

- [x] Generate a deterministic synthetic 100,000-paper corpus and run persistence, embeddings, sparse edges, and aggregate construction.
- [x] Record elapsed time, peak memory, database size, edge count, aggregate count, and scene payload size.
- [x] Run the full backend/frontend test suites and a real small OpenAlex build.
- [x] Keep the API and frontend running for acceptance testing.

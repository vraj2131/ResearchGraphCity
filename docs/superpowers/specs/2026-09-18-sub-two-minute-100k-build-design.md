# Sub-Two-Minute 100K Build Design

## Objective

Reduce the deterministic 100,000-paper compute pipeline from 530.774 seconds to less than 120 seconds on the same development machine without lowering the semantic-neighbor count from 20. Keep PostgreSQL/pgvector authoritative and preserve existing API and frontend behavior.

The two-minute gate starts after paper metadata is available locally. First-time OpenAlex network collection is measured separately because external latency and rate limits are not controlled by the application. A cached or snapshot-backed real-data build uses the same sub-two-minute compute path.

## Constraints

- Preserve `semantic_k=20`, citation edges, topic/attribute edges, maximum similarity degree 40, Leiden communities, floors, bridges, and streets.
- Do not modify `Graph-Cities/Graph_City_Web`.
- Keep builds asynchronous, cancellable, restart-safe, and PostgreSQL-backed.
- Never load paper-level data into the browser scene.
- Keep the existing JSON repository compatibility path.
- Do not send full graph data to Groq.

## Architecture

### City-scoped vector search

Load the city's normalized 64-dimensional embeddings once, construct one HNSW index scoped to that city, and query all sources in parallel. This replaces 100,000 SQL lateral nearest-neighbor queries. The implementation retains 20 neighbors per source and bulk-loads canonical pairs through a PostgreSQL staging table.

### Reusable global neighbor cache

Persist computed source/target/model/rank/similarity rows independently of a city. A later city reuses cached neighbors whose endpoints are members of that city and computes only sources that do not have a complete cached neighborhood. Cache rows are versioned by embedding model and neighbor algorithm.

### Bulk PostgreSQL writes

Use psycopg `COPY` into temporary staging tables, then merge set-wise into embeddings, memberships, semantic edges, and structure assignments. Existing uniqueness constraints remain the final consistency boundary.

### Parallel and snapshot-backed OpenAlex collection

Run independent seed/query streams through a bounded thread pool. Each worker owns an HTTP session; a shared limiter enforces configured request concurrency and minimum request interval. Continue using the PostgreSQL response cache and retries. Add a local JSONL snapshot provider implementing the same candidate interface so large builds can avoid remote pagination.

### Pipelined build stages

Expansion emits committed batches. Embedding is performed for each committed batch while collection continues, leaving only a final catch-up pass before graph construction. Edge construction waits for complete city membership because neighbor selection is city-scoped.

### Bulk city persistence

Keep Leiden and metric semantics unchanged, but pre-generate UUIDs, bulk-insert districts/buildings/floors/relationships, and update all paper assignments through one staging-table merge rather than thousands of per-building updates.

## Performance Gates

- 100,000 papers, `semantic_k=20`, and the existing deterministic corpus.
- Compute stages total less than 120 seconds on the same machine used for the 530.774-second baseline.
- Each stage and peak RSS recorded.
- Repeated-city benchmark records cache reuse and is no slower than the cold compute build.
- Edge count, citation count, maximum similarity degree, aggregate hierarchy, and scene payload remain valid.
- Backend tests pass in JSON and PostgreSQL modes; frontend tests and build remain green.

## Operational Semantics

The API reports collection and compute durations separately. A two-minute result is not claimed for uncached public API collection. Production deployments seeking predictable end-to-end timing must point `OPENALEX_SNAPSHOT_PATH` at a locally maintained OpenAlex work subset or warm the PostgreSQL ingestion cache before queuing the city.


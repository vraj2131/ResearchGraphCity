# 100K Build Operations

## Build behavior

A user submits 1–30 paper titles, DOIs, or OpenAlex IDs and chooses a target up to 100,000. The API only creates and queues the city. The worker performs seed resolution, seed preview, balanced collection, embeddings, sparse edges, original Graph Cities fixed-point/wave decomposition, and city persistence. Semantic districts and evidence bridges remain application overlays.

Run the worker separately from the API:

```bash
cd backend
../.venv/bin/python -m app.worker
```

Progress is persisted in `build_jobs`. Restarting a worker is safe because seed memberships, papers, embeddings, edges, and city aggregates use idempotent keys or stage replacement.

## Scale benchmark

The benchmark uses deterministic synthetic metadata and deletes its city afterward unless `--keep` is provided:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city \
  ../.venv/bin/python scripts/benchmark_100k.py --papers 100000 --semantic-k 20
```

The report includes stage durations, peak process memory, database size, retained edge count, aggregate counts, and serialized scene size. Run it against a disposable or development database, never the automated test database while tests are active.

### Current original Graph Cities result

The default benchmark algorithm is now `original` (`graph-cities-v1`). On 2026-09-26, 100,000 synthetic papers completed local processing in **102.979 seconds**, preserving one fixed-point building with **50,000 waves**. Peak RSS was 2.68 GB, scene gzip 4,806 bytes, building-paper retrieval p95 55.090 ms, search p95 86.517 ms and assistant retrieval p95 148.663 ms. Collection and remote LLM time are excluded.

See [full evidence and limitations](research/original-graph-cities-reference/verification.md) and [raw results](research/original-graph-cities-reference/benchmark-100k-final.json). Use `--algorithm leiden` only to reproduce the legacy comparison. Original fixed points are never split to meet a mesh or page limit; full memberships and waves remain in PostgreSQL, with sampled overview geometry and paginated details.

### Historical Leiden measurements

The following 2026-09-17/18 measurements and oversized-community optimizations describe the previous Leiden pipeline, not the default original Graph Cities decomposition.

### Verified 100,000-paper run

Run on 2026-09-17 against local PostgreSQL 16 with pgvector:

| Metric | Result |
| --- | ---: |
| Papers embedded | 100,000 |
| Retained paper edges | 1,188,188 |
| Buildings / floors | 463 / 1,352 |
| Districts | 6 |
| Bridges / streets | 3,355 / 462 |
| Aggregate scene JSON | 4,062,907 bytes |
| Peak process RSS | 2,061,975,552 bytes |
| Database size during run | 1,957,780,503 bytes |
| Persist / embed / edges / city | 37.589 / 33.337 / 383.493 / 99.690 seconds |
| Total pipeline time | 554.109 seconds |

The benchmark retained 99,999 citation edges and generated 1,993,730 bounded semantic candidates. It did not execute an all-pairs paper comparison. The browser scene remained aggregate-only; its payload contained 463 buildings rather than 100,000 paper nodes.

### Verified performance-gate run

Run on 2026-09-18 against the same local PostgreSQL 16/pgvector environment. This run includes the browser-transfer and indexed retrieval gates added after the first benchmark:

| Metric | Result | Gate |
| --- | ---: | ---: |
| Papers embedded | 100,000 | 100,000 |
| Retained paper edges | 1,192,929 | sparse construction |
| Buildings / floors | 641 / 1,982 | aggregate-only scene |
| Districts | 6 | hierarchy present |
| Bridges / streets | 4,020 / 640 | relationships present |
| Aggregate scene JSON | 5,214,611 bytes | diagnostic only |
| Aggregate scene gzip | 369,385 bytes | < 5 MB |
| Paper search p95 | 77.992 ms | < 500 ms |
| Building-paper pagination p95 | 20.393 ms | < 500 ms |
| Assistant retrieval p95 | 167.314 ms | < 1,000 ms |
| Peak process RSS | 2,165,800,960 bytes | recorded |
| Database size during run | 2,027,527,191 bytes | recorded |
| Persist / embed / edges / city | 37.117 / 25.366 / 365.662 / 102.628 seconds | recorded |
| Total pipeline time | 530.774 seconds | recorded |

The run generated 1,993,714 bounded semantic candidates and retained 1,092,930 similarity edges plus 99,999 citation edges. The uncompressed JSON size varies with the detected aggregate count; HTTP gzip is the transfer-size gate used by the browser.

### Verified sub-two-minute run

Run on 2026-09-19 against local PostgreSQL 16/pgvector on the baseline Apple Silicon development machine:

| Metric | Result | Gate |
| --- | ---: | ---: |
| Local compute total | **104.982 seconds** | **< 120 seconds** |
| Persist / embed / edges / city | 9.985 / 20.818 / 43.830 / 30.349 seconds | included in total |
| Papers embedded | 100,000 | 100,000 |
| Semantic candidates | 2,000,000 | `semantic_k=20` |
| Retained paper edges | 1,337,055 | sparse construction |
| Maximum similarity degree | 40 | <= 40 |
| Buildings / floors | 24 / 118 | aggregate-only scene |
| Bridges / streets | 24 / 23 | relationships present |
| Aggregate scene gzip | 21,997 bytes | < 5 MB |
| Paper search p95 | 112.930 ms | < 500 ms |
| Building-paper pagination p95 | 63.624 ms | < 500 ms |
| Assistant retrieval p95 | 164.848 ms | < 1,000 ms |
| Peak process RSS | 3,040,329,728 bytes | recorded |

The cold run computed neighbors for all 100,000 papers. A second edge build over the same corpus reported 100,000 neighbor-cache hits, zero recomputed sources, and 46.260 seconds for the complete warm edge rebuild. Reproduce both paths with:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city \
  ../.venv/bin/python scripts/benchmark_100k.py --papers 100000 --semantic-k 20 --measure-warm-cache
```

OpenAlex collection is reported separately from local compute because network latency and rate limits are external. Use `OPENALEX_SNAPSHOT_PATH` for deterministic local collection; parallel live collection remains available through `OPENALEX_WORKERS`.

The optimized path uses a city-scoped parallel HNSW index, compact reusable neighbor rows, direct parallel PostgreSQL COPY, 20,000-paper embedding batches, a degree-bounded community-detection backbone, and guarded oversized-community splitting. The full edge table remains available for metrics and inspection.

## Operational limits

- Main scene responses contain districts, buildings, floors, bridges, and streets only.
- Paper and edge detail pages are capped at 200 records.
- Non-citation similarity degree is capped at 40 per paper; citation edges remain explicit.
- OpenAlex responses are cached and retryable errors use bounded backoff.
- Cancellation is cooperative between API pages, persistence batches, embedding batches, and semantic-neighbor batches.

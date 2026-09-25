# Compatibility baseline, 2026-09-24

Recorded before original Graph Cities implementation. These results establish a baseline; they do not prove the new algorithm or migration works.

## Executed checks

- Backend: `STORAGE_BACKEND=postgres TEST_DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city_test ../.venv/bin/python -m pytest -q --tb=short` — 120 passed in 10.32 seconds.
- Frontend: `npm test -- --run` — 34 passed across 8 files.
- Frontend: `npm run build` — passed; existing warning for a JavaScript chunk over 500 kB. Output main JavaScript was 1,182.55 kB, 329.72 kB gzip.
- Development database was inspected read-only: Alembic `20260919_0008`, pgvector `0.8.6`.
- Ready legacy cities: Research Graph City, 1,000 papers / 13 buildings; Seeded Research Graph City, 991 papers / 14 buildings. Both report `legacy-v1`.
- Other development cities: one cancelled at 6,610 papers, one failed at 10 papers. Neither has a completed structure. No rebuild was queued by these checks.

## Membership-sensitive code requiring compatibility coverage

`backend/app/repositories/postgres_city.py` currently uses `CityPaperRecord.building_id` / `floor_id` in:

- building paper retrieval and floor filters;
- building internal edge retrieval (currently an induced subgraph on selected members);
- bridge cross-edge retrieval;
- paper search and single-paper lookup joins;
- building filters on search;
- timeline distinct building counts.

Original decomposition needs explicit edge ownership and overlapping vertex membership. Tests must verify that a shared paper can be found from every assigned building, while global search and timeline paper counts do not multiply it. Counting all edges between member vertices is insufficient for a fixed-point building if some of those edges belong to another layer.

`backend/app/assistant.py` derives valid scene targets and claims from retrieved paper/building/relationship records. `relationships_for_buildings` currently returns streets without excluding geometric relationships. The legacy city-navigation packet in `backend/app/main.py` similarly includes all streets. Both assistant paths must distinguish research evidence from geometry before original streets are introduced.

## Rendering and original-street findings

`frontend/src/sceneLayout.ts` currently translates and uniformly scales building coordinates to fit a radius of 260. It does not replace their ordering or topology, but leaves footprints unscaled. Preserve original relative positions and verify that fitting does not cause overlaps; do not describe the existing code as reclustering buildings.

Original `Graph_City_Web/python/preprocess.py` uses SciPy Voronoi `ridge_points` for building-neighbor pairs (the Delaunay dual). For fewer than four buildings it emits every pair. `path.py` attaches Euclidean lengths to those neighbors. Reference tests should exercise this actual implementation, including small graphs and degenerate coordinates, instead of relying only on the README's description of triangulation.

The existing database, credentials, Docker volume, LLM provider configuration, and pgvector indexes have not been changed by this investigation.

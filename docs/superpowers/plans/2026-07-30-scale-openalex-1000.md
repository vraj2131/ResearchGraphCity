# Scale OpenAlex To 1000 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale Research Graph City ingestion from a single 300-work OpenAlex pull to a paginated 1000-paper dataset without breaking current API or frontend behavior.

**Architecture:** Add cursor pagination in `backend/app/openalex.py`, keep DOI/OpenAlex dedupe centralized, and expose `--target-total` through `backend/scripts/build_research_city.py`. Existing graph construction, processed JSON format, API endpoints, and frontend rendering stay compatible.

**Tech Stack:** Python, requests, pytest, FastAPI processed JSON, existing Vite/React frontend.

## Global Constraints

- Do not modify `Graph-Cities/Graph_City_Web`.
- OpenAlex `per_page` remains capped at 100.
- Use `OPENALEX_API_KEY` from the existing project environment when present.
- Preserve existing processed JSON filenames under `ResearchGraphCity/data/processed/`.
- Keep existing backend and frontend tests passing.

---

### Task 1: Paginated OpenAlex Fetch

**Files:**
- Modify: `backend/app/openalex.py`
- Modify: `backend/tests/test_processing.py`

**Interfaces:**
- Consumes: `fetch_openalex_works(queries=SEED_QUERIES, per_query=100)`
- Produces: `fetch_openalex_works(queries=SEED_QUERIES, per_query=100, target_total=None) -> list[dict]`

- [ ] **Step 1: Write failing pagination tests**
  - Add a test that stubs `requests.get` and expects `cursor=*`, then `cursor=<next_cursor>`.
  - Add a test that verifies the final returned list stops at `target_total`.

- [ ] **Step 2: Run focused tests**
  - Run: `.venv/bin/python -m pytest tests/test_processing.py -q`
  - Expected: pagination tests fail because `target_total` is unsupported.

- [ ] **Step 3: Implement cursor pagination**
  - Update `fetch_openalex_works` to loop pages for each query.
  - Use `per_page=min(per_query, 100)`.
  - Include `cursor` in params.
  - Read `meta.next_cursor`.
  - Dedupe incrementally and stop at `target_total`.

- [ ] **Step 4: Run focused tests**
  - Run: `.venv/bin/python -m pytest tests/test_processing.py -q`
  - Expected: pass.

### Task 2: CLI Target Total

**Files:**
- Modify: `backend/scripts/build_research_city.py`
- Modify: `backend/app/openalex.py`

**Interfaces:**
- Consumes: `build_city_from_openalex(processed_dir, per_query=100)`
- Produces: `build_city_from_openalex(processed_dir, per_query=100, target_total=1000)`

- [ ] **Step 1: Write failing CLI-adjacent test**
  - Add a test that patches `fetch_openalex_works` and verifies `build_city_from_openalex(..., target_total=1000)` forwards the value.

- [ ] **Step 2: Run focused test**
  - Run: `.venv/bin/python -m pytest tests/test_processing.py::<new_test> -q`
  - Expected: fail because `build_city_from_openalex` does not accept `target_total`.

- [ ] **Step 3: Implement CLI args**
  - Add `argparse` in `scripts/build_research_city.py`.
  - Support `--target-total 1000` and `--per-query 100`.
  - Print output counts after generation.

- [ ] **Step 4: Run focused tests**
  - Run: `.venv/bin/python -m pytest tests/test_processing.py -q`
  - Expected: pass.

### Task 3: Regenerate 1000-Paper City And Verify

**Files:**
- Modify generated data in `data/processed/*.json`

**Interfaces:**
- Consumes: `python scripts/build_research_city.py --target-total 1000`
- Produces: processed JSON with approximately 1000 deduped paper vertices.

- [ ] **Step 1: Run full tests before ingestion**
  - Backend: `.venv/bin/python -m pytest tests -q`
  - Frontend: `npm test -- --run`

- [ ] **Step 2: Run ingestion**
  - From `ResearchGraphCity/backend`: `.venv/bin/python scripts/build_research_city.py --target-total 1000`
  - Expected: writes processed JSON and prints counts.

- [ ] **Step 3: Verify generated data**
  - Count vertices, edges, buildings, floors, bridges, communities.
  - Confirm vertex count is 1000 unless OpenAlex returns fewer unique works.

- [ ] **Step 4: Run full verification**
  - Backend: `.venv/bin/python -m pytest tests -q`
  - Frontend: `npm test -- --run`
  - Frontend build: `npm run build`
  - Original repo: `git -C ../Graph-Cities status --short`

# Seeded City Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user paste a small list of seed papers and build a new graph city from about 1000 related OpenAlex papers using the same graph-city rules.

**Architecture:** Add a backend seeded ingestion path that resolves seed paper titles/DOIs/OpenAlex URLs, expands related OpenAlex works, builds a city with the existing graph pipeline, and writes `seeded_*.json` files. Add generic city endpoints for `research` and `seeded`, then update the frontend to load either city and provide a simple seed text box.

**Tech Stack:** FastAPI, Pydantic, OpenAlex requests, existing NetworkX graph pipeline, Vite React TypeScript, Zustand.

## Global Constraints

- Do not modify `Graph-Cities/Graph_City_Web`.
- Keep user input simple: one paper title, DOI, or OpenAlex URL per line.
- Reuse the same buildings, floors, bridges, streets, communities, inspectors, and rendering rules.
- Do not create layout-only streets or zero-score research streets.
- Default seeded expansion target is 1000 papers.

---

### Task 1: Backend Seeded City Pipeline

**Files:**
- Modify: `ResearchGraphCity/backend/app/schemas.py`
- Modify: `ResearchGraphCity/backend/app/openalex.py`
- Modify: `ResearchGraphCity/backend/app/graph_processing.py`
- Test: `ResearchGraphCity/backend/tests/test_processing.py`
- Test: `ResearchGraphCity/backend/tests/test_api.py`

**Interfaces:**
- Produces: `parse_seed_text(seed_text: str) -> list[str]`
- Produces: `build_city_from_seed_inputs(seed_inputs: list[str], processed_dir: Path, target_total: int = 1000, per_query: int = 100) -> ResearchCity`
- Produces: `write_processed_city(city, processed_dir, prefix="research")`

- [ ] Write failing backend tests for seed parsing, seeded city build with monkeypatched OpenAlex works, and `seeded_*.json` output.
- [ ] Implement seed parsing and seeded city build.
- [ ] Extend `ResearchVertex` with `seeded`, `seed_input`, `seed_rank`, and `seed_relevance`.
- [ ] Make processed JSON writer accept `prefix`.
- [ ] Run backend focused tests.

### Task 2: Backend Seeded API

**Files:**
- Modify: `ResearchGraphCity/backend/app/main.py`
- Test: `ResearchGraphCity/backend/tests/test_api.py`

**Interfaces:**
- Produces: `POST /api/cities/seeded/build`
- Produces: `GET /api/cities/{city_id}/buildings`
- Produces: `GET /api/cities/{city_id}/bridges`
- Produces: `GET /api/cities/{city_id}/streets`
- Produces: `GET /api/cities/{city_id}/communities`
- Produces: seeded building/bridge paper-edge inspector endpoints.

- [ ] Write failing API tests for building a seeded city and reading seeded endpoints.
- [ ] Implement generic city file helpers for `research` and `seeded`.
- [ ] Implement seeded build endpoint.
- [ ] Run backend API tests.

### Task 3: Frontend Seed Input and City Mode

**Files:**
- Modify: `ResearchGraphCity/frontend/src/types.ts`
- Modify: `ResearchGraphCity/frontend/src/api.ts`
- Modify: `ResearchGraphCity/frontend/src/store.ts`
- Modify: `ResearchGraphCity/frontend/src/App.tsx`
- Modify: `ResearchGraphCity/frontend/src/Inspector.tsx`
- Test: `ResearchGraphCity/frontend/src/App.test.tsx`
- Test: `ResearchGraphCity/frontend/src/api.test.ts`

**Interfaces:**
- Produces: `buildSeededCity(seedText: string)`.
- Produces: frontend city mode `research | seeded`.

- [ ] Write failing frontend tests for submitting seed text and loading seeded city data.
- [ ] Implement API functions with city mode path prefixes.
- [ ] Add simple seed textarea and build button.
- [ ] Pass city mode into inspectors so paper/edge endpoints match selected city.
- [ ] Run focused frontend tests.

### Task 4: Verification

**Files:**
- Existing test and app files only.

- [ ] Run backend tests: `../.venv/bin/python -m pytest tests -q`.
- [ ] Run frontend tests: `npm test -- --run`.
- [ ] Run frontend build: `npm run build`.
- [ ] Verify `Graph-Cities` status is clean.
- [ ] Restart frontend on `5173` and verify API smoke checks.


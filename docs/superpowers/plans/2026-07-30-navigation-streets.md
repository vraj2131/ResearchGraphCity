# Navigation Streets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add original-Graph-City-inspired navigation streets as a separate non-breaking layer so every building is connected without weakening the meaning of evidence bridges.

**Architecture:** Backend generates `Street` records from building positions using a minimum spanning tree plus nearest-neighbor reinforcement, stores them as `research_streets.json`, and exposes `/api/cities/research/streets`. Frontend loads streets alongside buildings/bridges, renders streets as thin neutral ground roads, keeps bridges as clickable blue evidence roads, and adds a separate layer toggle and count.

**Tech Stack:** Python, Pydantic, NetworkX, FastAPI, pytest, React, TypeScript, React Three Fiber, Vitest.

## Global Constraints

- Do not modify `Graph-Cities/Graph_City_Web`.
- Existing `bridges` remain evidence-backed research relationships.
- New `streets` are layout/navigation connections and do not drive summaries.
- Existing processed JSON filenames and endpoints remain compatible.
- Keep backend tests, frontend tests, and frontend build passing.

---

### Task 1: Backend Street Generation And API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/graph_processing.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_processing.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `Street` schema with `street_id`, `source_building_id`, `target_building_id`, `street_type`, `distance`, `evidence`.
- Produces: `build_streets(buildings: list[Building]) -> list[Street]`.
- Produces: `GET /api/cities/research/streets`.

- [ ] Write failing tests proving street generation connects all buildings and marks MST streets as navigation streets.
- [ ] Write failing API test for `/api/cities/research/streets`.
- [ ] Implement `Street`, `ResearchCity.streets`, `build_streets`, JSON writing, and API route.
- [ ] Run focused backend tests.

### Task 2: Frontend Streets Layer

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/CityScene.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `Street[]` from `fetchResearchCity`.
- Adds: `layers.streets`.
- Renders: `StreetRoad` as non-clickable neutral ground road.

- [ ] Write failing frontend test proving city loads street count and toggles Streets separately from Bridges.
- [ ] Implement TypeScript street types, API fetch, store state, app stats/toggle, scene prop, and street rendering.
- [ ] Run focused frontend tests.

### Task 3: Regenerate Data And Verify

**Files:**
- Modify generated: `data/processed/research_streets.json`
- Modify generated existing city files only as produced by current pipeline.

**Interfaces:**
- Consumes: `../.venv/bin/python scripts/build_research_city.py --target-total 1000 --per-query 100`.
- Produces: processed city with evidence bridges plus navigation streets.

- [ ] Run backend and frontend tests before regeneration.
- [ ] Regenerate processed data.
- [ ] Confirm all 15 current buildings have street degree at least 1.
- [ ] Run backend tests, frontend tests, and frontend build.
- [ ] Restart backend/frontend and smoke-test `/api/cities/research/streets`.

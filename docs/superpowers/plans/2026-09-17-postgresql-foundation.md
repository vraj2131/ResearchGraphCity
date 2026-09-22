# PostgreSQL Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace live JSON scans with PostgreSQL-backed city persistence and add durable asynchronous city build jobs without breaking the existing 1,000-paper application.

**Architecture:** Add SQLAlchemy models and repositories behind a storage abstraction, migrate existing JSON cities into PostgreSQL, and run builds through a PostgreSQL `SKIP LOCKED` queue consumed by a standalone worker. Existing read endpoints retain their response shapes and can use `STORAGE_BACKEND=json` until parity is verified.

**Tech Stack:** PostgreSQL 16, pgvector, SQLAlchemy 2, Psycopg 3, Alembic, FastAPI, pytest, Docker Compose, React, TypeScript, Vitest.

**Spec:** `ResearchGraphCity/docs/superpowers/specs/2026-09-17-research-graph-city-100k-platform-design.md`

## Global Constraints

- Do not modify `Graph-Cities/Graph_City_Web`.
- PostgreSQL with pgvector becomes the active live data store after migration verification.
- Preserve existing building, bridge, street, community, paper, and edge API payloads.
- Accept 1 to 30 seed inputs and target counts from 10 through 100,000.
- A 100,000-paper build must be asynchronous and must never execute inside the request handler.
- API keys remain server-side and must never be logged.
- JSON remains an import/export and development fallback during migration.
- This workspace is not a Git repository, so commit steps are intentionally omitted.

---

### Task 1: Database Runtime And Configuration

**Files:**
- Create: `ResearchGraphCity/docker-compose.yml`
- Create: `ResearchGraphCity/backend/alembic.ini`
- Create: `ResearchGraphCity/backend/alembic/env.py`
- Create: `ResearchGraphCity/backend/alembic/script.py.mako`
- Modify: `ResearchGraphCity/backend/requirements.txt`
- Modify: `ResearchGraphCity/.env.example`
- Modify: `ResearchGraphCity/backend/app/config.py`
- Test: `ResearchGraphCity/backend/tests/test_config.py`

**Interfaces:**
- Produces: `settings.database_url: str`, `settings.storage_backend: Literal["json", "postgres"]`, `settings.worker_poll_seconds: float`, and `settings.job_stale_seconds: int`.
- Produces: local PostgreSQL service on port `55432` with database/user/password `research_graph_city`.

- [x] **Step 1: Write failing configuration tests**

```python
def test_database_settings_have_safe_local_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    settings = load_settings()
    assert settings.storage_backend == "json"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.job_stale_seconds >= 60
```

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_config.py -q`

Expected: failure because database and worker settings are absent.

- [x] **Step 3: Add dependencies and runtime files**

Add exact compatible dependencies for SQLAlchemy 2, Psycopg 3 binary, Alembic, and pgvector Python integration. Configure `docker-compose.yml` with `pgvector/pgvector:pg16`, a health check using `pg_isready`, a named volume, and port `55432:5432`.

- [x] **Step 4: Implement typed settings**

`load_settings()` must load the project `.env`, validate `STORAGE_BACKEND`, and default to JSON so existing users can run without PostgreSQL. The example environment adds:

```dotenv
DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city
STORAGE_BACKEND=json
WORKER_POLL_SECONDS=1.0
JOB_STALE_SECONDS=300
EMBEDDING_MODEL=tfidf-svd-64
```

- [x] **Step 5: Run focused tests**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_config.py -q`

Expected: all configuration tests pass.

### Task 2: SQLAlchemy Schema And Alembic Migration

**Files:**
- Create: `ResearchGraphCity/backend/app/db.py`
- Create: `ResearchGraphCity/backend/app/models.py`
- Create: `ResearchGraphCity/backend/alembic/versions/20260917_0001_platform_schema.py`
- Test: `ResearchGraphCity/backend/tests/test_database.py`

**Interfaces:**
- Produces: `Base`, `create_engine_from_settings()`, `session_scope()`, and `check_database()`.
- Produces ORM models for `CityRecord`, `CitySeedRecord`, `PaperRecord`, `PaperEmbeddingRecord`, `CityPaperRecord`, `PaperReferenceRecord`, `PaperEdgeRecord`, `DistrictRecord`, `BuildingRecord`, `FloorRecord`, `BuildingRelationshipRecord`, `CommunityRunRecord`, `CitySnapshotRecord`, `BuildJobRecord`, `IngestionCacheRecord`, `AssistantConversationRecord`, `AssistantMessageRecord`, and `AnswerCitationRecord`.

- [x] **Step 1: Write migration/model tests**

```python
def test_schema_contains_required_platform_tables(database_engine):
    command.up(alembic_config, "head")
    tables = set(inspect(database_engine).get_table_names())
    assert {"cities", "papers", "city_papers", "paper_edges", "build_jobs", "buildings", "floors"} <= tables

def test_city_target_accepts_100000(database_session):
    city = CityRecord(name="Scale test", kind="seeded", status="draft", target_paper_count=100_000, configuration={})
    database_session.add(city)
    database_session.commit()
    assert city.target_paper_count == 100_000
```

- [x] **Step 2: Run tests against the PostgreSQL test database and confirm failure**

Run: `cd ResearchGraphCity/backend && TEST_DATABASE_URL=$DATABASE_URL ../.venv/bin/python -m pytest tests/test_database.py -q`

Expected: failure because database modules and migration do not exist.

- [x] **Step 3: Implement database lifecycle and ORM models**

Use UUID primary keys for city-owned aggregate records, canonical OpenAlex IDs for papers, JSONB for evidence and source metadata, and bounded string status fields with check constraints. Store external display IDs such as `B_R_0001` in unique `(city_id, external_id)` columns.

- [x] **Step 4: Implement initial migration**

The migration must run `CREATE EXTENSION IF NOT EXISTS vector`, create every table and foreign key from the design, add GIN full-text indexes, city/building/paper indexes, and downgrade in reverse dependency order.

- [x] **Step 5: Verify upgrade and downgrade**

Run:

```bash
cd ResearchGraphCity/backend
../.venv/bin/alembic upgrade head
../.venv/bin/alembic downgrade base
../.venv/bin/alembic upgrade head
../.venv/bin/python -m pytest tests/test_database.py -q
```

Expected: migration round trip succeeds and database tests pass.

### Task 3: City Repository Boundary

**Files:**
- Create: `ResearchGraphCity/backend/app/repositories/__init__.py`
- Create: `ResearchGraphCity/backend/app/repositories/protocols.py`
- Create: `ResearchGraphCity/backend/app/repositories/json_city.py`
- Create: `ResearchGraphCity/backend/app/repositories/postgres_city.py`
- Create: `ResearchGraphCity/backend/app/repositories/factory.py`
- Modify: `ResearchGraphCity/backend/app/main.py`
- Test: `ResearchGraphCity/backend/tests/test_repositories.py`
- Test: `ResearchGraphCity/backend/tests/test_api.py`

**Interfaces:**
- Produces: `CityRepository` protocol.
- Produces: `JsonCityRepository(processed_dir: Path)` and `PostgresCityRepository(session_factory)`.
- Produces: `get_city_repository(settings, processed_dir) -> CityRepository`.
- Repository methods: `list_cities`, `get_city`, `get_scene`, `get_building`, `get_bridge`, `get_street`, `get_building_papers`, `get_building_edges`, and `get_bridge_edges`.

- [x] **Step 1: Add repository contract tests**

```python
@pytest.mark.parametrize("repository_fixture", ["json_repository", "postgres_repository"])
def test_repository_scene_contract(request, repository_fixture):
    repo = request.getfixturevalue(repository_fixture)
    scene = repo.get_scene("research")
    assert scene.buildings
    assert all(item.external_id for item in scene.buildings)
```

- [x] **Step 2: Run tests and confirm missing repository failure**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_repositories.py tests/test_api.py -q`

- [x] **Step 3: Move existing JSON reads behind `JsonCityRepository`**

Do not change current JSON payload semantics. The FastAPI route functions obtain a repository through dependency injection instead of calling `read_json` directly.

- [x] **Step 4: Implement PostgreSQL reads with bounded queries**

Paper and edge methods accept `limit <= 200`, cursor, and optional floor ID. Aggregate scene queries never join or serialize all city papers.

- [x] **Step 5: Run repository and API tests for both backends**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_repositories.py tests/test_api.py -q`

Expected: both repository implementations satisfy the same aggregate contracts.

### Task 4: Legacy JSON Import

**Files:**
- Create: `ResearchGraphCity/backend/app/import_legacy.py`
- Create: `ResearchGraphCity/backend/scripts/import_legacy_city.py`
- Test: `ResearchGraphCity/backend/tests/test_legacy_import.py`

**Interfaces:**
- Produces: `import_legacy_city(processed_dir: Path, city_prefix: str, repository: PostgresCityRepository) -> ImportCounts`.
- CLI: `python scripts/import_legacy_city.py --prefix research --replace`.

- [x] **Step 1: Write idempotent import tests**

```python
def test_import_is_idempotent(postgres_repository, processed_fixture):
    first = import_legacy_city(processed_fixture, "research", postgres_repository)
    second = import_legacy_city(processed_fixture, "research", postgres_repository)
    assert first.paper_count == second.paper_count
    assert postgres_repository.get_city("research").paper_count == first.paper_count
```

- [x] **Step 2: Run the focused test and confirm failure**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_legacy_import.py -q`

- [x] **Step 3: Implement streaming import**

Read one JSON artifact at a time, upsert global papers, bulk insert city memberships and edges in batches of 2,000, and preserve existing external IDs, metrics, labels, geometry, summaries, and evidence.

- [x] **Step 4: Add parity checks**

After import, compare counts and representative IDs from JSON and PostgreSQL. Abort the CLI with a nonzero exit code on mismatch.

- [x] **Step 5: Run imports and parity tests**

Run:

```bash
cd ResearchGraphCity/backend
../.venv/bin/python -m pytest tests/test_legacy_import.py -q
../.venv/bin/python scripts/import_legacy_city.py --prefix research --replace
../.venv/bin/python scripts/import_legacy_city.py --prefix seeded --replace
```

Expected: existing cities are queryable from PostgreSQL with matching aggregate counts.

### Task 5: Durable PostgreSQL Job Queue

**Files:**
- Create: `ResearchGraphCity/backend/app/jobs.py`
- Create: `ResearchGraphCity/backend/app/worker.py`
- Test: `ResearchGraphCity/backend/tests/test_jobs.py`

**Interfaces:**
- Produces: `JobRepository.enqueue(city_id, stage="resolve") -> BuildJob`.
- Produces: `JobRepository.claim_next(worker_id) -> BuildJob | None` using `FOR UPDATE SKIP LOCKED`.
- Produces: `heartbeat`, `update_progress`, `request_cancel`, `finish`, `fail`, and `requeue_stale`.
- Produces: `run_worker(settings, once: bool = False) -> None`.

- [x] **Step 1: Write queue concurrency and lifecycle tests**

```python
def test_two_workers_cannot_claim_same_job(job_repository):
    queued = job_repository.enqueue(city_id)
    first = job_repository.claim_next("worker-a")
    second = job_repository.claim_next("worker-b")
    assert first.id == queued.id
    assert second is None

def test_cancel_is_cooperative(job_repository):
    job = job_repository.enqueue(city_id)
    job_repository.request_cancel(job.id)
    assert job_repository.should_cancel(job.id) is True
```

- [x] **Step 2: Run tests and confirm missing queue behavior**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_jobs.py -q`

- [x] **Step 3: Implement atomic job claims and lifecycle updates**

All transitions validate the prior state. Progress is monotonic within a stage. Failures store a sanitized structured error without API keys or full prompts.

- [x] **Step 4: Implement worker loop and handler registry**

The initial handler delegates small compatibility builds to the existing pipeline, but execution occurs only in the worker. The registry is stage-based so Program 2 can replace it with resumable ingestion stages.

- [x] **Step 5: Run queue tests including two concurrent sessions**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_jobs.py -q`

Expected: one claim, durable progress, cancellation, stale requeue, success, and failure paths pass.

### Task 6: Asynchronous City Lifecycle API

**Files:**
- Modify: `ResearchGraphCity/backend/app/schemas.py`
- Create: `ResearchGraphCity/backend/app/routes/__init__.py`
- Create: `ResearchGraphCity/backend/app/routes/cities.py`
- Create: `ResearchGraphCity/backend/app/routes/jobs.py`
- Modify: `ResearchGraphCity/backend/app/main.py`
- Test: `ResearchGraphCity/backend/tests/test_city_lifecycle_api.py`

**Interfaces:**
- Produces: `POST /api/cities`.
- Produces: `GET /api/cities/{city_id}`.
- Produces: `POST /api/cities/{city_id}/build` returning HTTP 202.
- Produces: `GET /api/jobs/{job_id}`.
- Produces: `POST /api/jobs/{job_id}/cancel`.
- Produces: compatibility `POST /api/cities/seeded/build` returning a job instead of blocking when PostgreSQL is active.

- [x] **Step 1: Write lifecycle API tests**

```python
def test_create_accepts_thirty_seeds_and_100000(client):
    response = client.post("/api/cities", json={"name": "Large city", "seed_inputs": [f"paper {i}" for i in range(30)], "target_paper_count": 100_000})
    assert response.status_code == 201

def test_build_is_queued_not_executed_in_request(client, build_spy):
    response = client.post(f"/api/cities/{city_id}/build")
    assert response.status_code == 202
    assert build_spy.call_count == 0
```

- [x] **Step 2: Run tests and confirm route/schema failure**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_city_lifecycle_api.py -q`

- [x] **Step 3: Implement request/response schemas**

Reject more than 30 inputs, blank-only input, duplicates after normalization when no unique seed remains, and targets outside 10 to 100,000. Return duplicate warnings without rejecting otherwise valid requests.

- [x] **Step 4: Implement routes and repository dependencies**

Creating a city does not call OpenAlex. Building only enqueues a job. Job status includes stage, progress, message, timestamps, warnings, sanitized error, and cancellation state.

- [x] **Step 5: Run lifecycle and complete API tests**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python -m pytest tests/test_city_lifecycle_api.py tests/test_api.py -q`

Expected: lifecycle API passes and existing endpoints remain compatible.

### Task 7: Frontend Job Submission And Progress

**Files:**
- Modify: `ResearchGraphCity/frontend/src/types.ts`
- Modify: `ResearchGraphCity/frontend/src/api.ts`
- Modify: `ResearchGraphCity/frontend/src/store.ts`
- Modify: `ResearchGraphCity/frontend/src/App.tsx`
- Test: `ResearchGraphCity/frontend/src/api.test.ts`
- Test: `ResearchGraphCity/frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `createCity`, `queueCityBuild`, `fetchBuildJob`, and `cancelBuildJob`.
- Produces: target selector values `1000 | 10000 | 25000 | 50000 | 100000`.
- Produces: resumable UI polling keyed by persisted `jobId`.

- [x] **Step 1: Write failing frontend tests**

```typescript
it('submits 30 seeds and a 100000 target then polls the returned job', async () => {
  await user.selectOptions(screen.getByLabelText(/target papers/i), '100000');
  await user.click(screen.getByRole('button', { name: /build seeded city/i }));
  expect(fetchMock).toHaveBeenCalledWith('/api/cities', expect.objectContaining({ method: 'POST' }));
  expect(await screen.findByText(/queued/i)).toBeInTheDocument();
});
```

- [x] **Step 2: Run tests and confirm failure**

Run: `cd ResearchGraphCity/frontend && npm test -- --run src/api.test.ts src/App.test.tsx`

- [x] **Step 3: Implement typed API and store lifecycle**

Poll no faster than once per second, stop on terminal states, persist active city/job IDs in local storage, and expose a cancel command.

- [x] **Step 4: Update the existing seed panel**

Keep one-paper-per-line input. Add input count, duplicate count, target selector, stage/progress display, retry-safe error copy, and cancel control. Do not add advanced graph settings to this form.

- [x] **Step 5: Run frontend tests and production build**

Run:

```bash
cd ResearchGraphCity/frontend
npm test -- --run
npm run build
```

Expected: all tests and TypeScript/Vite build pass.

### Task 8: Foundation Verification And Backend Switch

**Files:**
- Create: `ResearchGraphCity/backend/scripts/verify_postgres_parity.py`
- Create: `ResearchGraphCity/docs/postgresql-development.md`
- Modify: `ResearchGraphCity/.env.example`

**Interfaces:**
- Produces: parity command comparing JSON and PostgreSQL city counts and representative records.
- Produces: documented startup sequence for database, migrations, import, API, worker, and frontend.

- [x] **Step 1: Run complete backend tests in JSON mode**

Run: `cd ResearchGraphCity/backend && STORAGE_BACKEND=json ../.venv/bin/python -m pytest tests -q`

- [x] **Step 2: Run complete backend tests in PostgreSQL mode**

Run: `cd ResearchGraphCity/backend && STORAGE_BACKEND=postgres ../.venv/bin/python -m pytest tests -q`

- [x] **Step 3: Run parity verification**

Run: `cd ResearchGraphCity/backend && ../.venv/bin/python scripts/verify_postgres_parity.py`

Expected: research and seeded city aggregate counts and sampled object IDs match.

- [x] **Step 4: Run worker smoke test**

Create a 10-paper fake-source city, queue it, run `python -m app.worker --once`, and confirm the job reaches `succeeded` without building in the API process.

- [x] **Step 5: Run frontend verification**

Run: `cd ResearchGraphCity/frontend && npm test -- --run && npm run build`

- [x] **Step 6: Verify original application remains untouched**

Run: `git -C Graph-Cities status --short`

Expected: no changes under `Graph-Cities/Graph_City_Web`.

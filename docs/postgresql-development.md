# PostgreSQL Development

The scalable application uses PostgreSQL 16 with pgvector. JSON remains available as a read-only compatibility mode for the existing generated cities.

## One-time setup

```bash
docker compose up -d postgres
docker compose exec -T postgres createdb -U research_graph_city research_graph_city_test
docker compose exec -T postgres psql -U research_graph_city -d research_graph_city_test -c 'CREATE EXTENSION IF NOT EXISTS vector;'
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/python scripts/import_legacy_city.py --prefix research --replace
../.venv/bin/python scripts/import_legacy_city.py --prefix seeded --replace
../.venv/bin/python scripts/verify_postgres_parity.py
```

The development database is `research_graph_city`. Automated tests must use `research_graph_city_test` because database tests create and remove their own schema.

## Run the application

Use three terminals from `ResearchGraphCity/`:

```bash
cd backend
STORAGE_BACKEND=postgres ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8011
```

```bash
cd backend
STORAGE_BACKEND=postgres ../.venv/bin/python -m app.worker
```

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`.

## Tests

```bash
cd backend
STORAGE_BACKEND=json TEST_DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city_test ../.venv/bin/python -m pytest tests -q
STORAGE_BACKEND=postgres TEST_DATABASE_URL=postgresql+psycopg://research_graph_city:research_graph_city@127.0.0.1:55432/research_graph_city_test ../.venv/bin/python -m pytest tests -q
cd ../frontend
npm test -- --run
npm run build
```

Do not point `TEST_DATABASE_URL` at the development database.

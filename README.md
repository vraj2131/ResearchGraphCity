# Research Graph City

Explore research papers as an interactive 3D city. The project combines OpenAlex paper discovery, graph processing, community detection, and a research assistant with a React and Three.js interface.

## Project layout

- `backend/`: FastAPI API, background worker, graph pipeline, PostgreSQL migrations, and tests.
- `frontend/`: React, TypeScript, and React Three Fiber interface.
- `data/processed/`: Generated research and seeded city datasets.
- `docs/`: Setup instructions, operations notes, research reports, and development plans.

## Local setup

From the repository root, create a Python environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd frontend
npm ci
cd ..
```

Configure local credentials in `.env`. OpenAlex and Groq settings are provided in `.env.example`; actual credentials are excluded from Git.

Follow [PostgreSQL development](docs/postgresql-development.md) to start PostgreSQL with pgvector, apply migrations, import the bundled cities, and run the API, worker, and frontend.

See [100K build operations](docs/100k-operations.md) for pipeline behavior, benchmark commands, and recorded performance results.

## Validation

Backend test setup and commands are in [PostgreSQL development](docs/postgresql-development.md). Frontend tests and production build:

```bash
cd frontend
npm test
npm run build
```

## Research materials

- [Progress report](docs/research_graph_city_progress_report.pdf)
- [Five-minute presentation](ResearchGraphCity_5min_presentation.html)

This repository contains the ResearchGraphCity project. The related upstream Graph Cities project is available at [endlesstory0428/Graph-Cities](https://github.com/endlesstory0428/Graph-Cities).

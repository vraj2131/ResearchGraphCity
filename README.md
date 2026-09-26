# Research Graph City

Explore research papers as an interactive 3D city. New worker builds use the original Graph Cities fixed-point edge decomposition and wave/fragment method, with OpenAlex paper discovery and a research assistant in a React and Three.js interface.

## Graph Cities method

The implementation is self-contained: normal installation, tests, and execution do not require a sibling `Graph-Cities` checkout. Available original source, license notices, source revisions, and executable-output parity fixtures are preserved under [`backend/vendor/graph_cities`](backend/vendor/graph_cities/README.md). The wave stage is a local Python implementation checked against the original executable, rather than a claim that unavailable original source was copied.

New cities record `graph-cities-v1`. Citation edges form a simple undirected decomposition graph; directed citations and similarity links remain available as research evidence. Connected fixed points become buildings, with wave floors and fragment metadata. Papers can occur in several buildings. Papers without citation edges remain in an explicitly labeled isolate representation. Legacy cities retain their original algorithm and remain readable.

The layout follows original bucket/spiral formulas and geometric street adjacency. Semantic districts, evidence-backed bridges, embeddings, and the Groq assistant are application extensions. Geometric streets are labeled separately and excluded from assistant evidence. Setting a city's `graph_input` configuration to `citation-plus-similarity` records an explicit experimental input; it is not the default.

Large buildings keep every wave in PostgreSQL. The city scene samples at most 64 wave floors per building and interpolates its overview geometry; the inspector's floor pages access every stored wave, and paper/edge pages support focused browsing beyond the preview. A 100,000-paper target is an ingestion ceiling, not a guarantee that OpenAlex has enough reachable records or that the resulting graph contains many buildings.

See the [integration verification and UI walkthrough](docs/research/original-graph-cities-reference/verification.md) for reference checks, compatibility evidence and the measured 100k run.

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

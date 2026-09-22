# Evidence-Grounded Research Assistant

## Goal

Replace route-only navigation with bounded PostgreSQL retrieval and structured answers about papers, domains, buildings, districts, relationships, and optional city routes.

## Tasks

### Task 1: Search And Retrieval

- [x] Add indexed full-text maintenance for paper title and abstract.
- [x] Add bounded hybrid lexical/vector paper retrieval with research filters.
- [x] Expose paper search and individual paper detail endpoints.

### Task 2: Evidence Packets

- [x] Attach each result to its building and district context.
- [x] Retrieve only relationships relevant to the selected evidence.
- [x] Cap packets independently of city size.

### Task 3: Grounded Synthesis

- [x] Add strict assistant request/response schemas.
- [x] Generate Groq JSON from evidence packets and validate all cited IDs.
- [x] Return useful retrieval results and evidence-derived confidence without Groq.

### Task 4: Workspace UI

- [x] Replace the route-only navigator with domain and paper answers.
- [x] Make cited buildings, relationships, and papers clickable.
- [x] Preserve route steps and selected-object highlighting.

### Task 5: Verification

- [x] Verify ranking, filters, packet limits, citation rejection, and fallback.
- [x] Run backend tests in JSON and PostgreSQL modes.
- [x] Run frontend tests/build and smoke-test the live endpoint.

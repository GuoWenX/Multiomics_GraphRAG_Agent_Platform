# Multiomics GraphRAG Agent Platform

Web-based intelligent agent workbench for biomedical multi-omics analysis, Neo4j knowledge graph exploration, and GraphRAG-assisted Q&A.

## Overview

The platform combines a FastAPI backend with a Vue 3 Vite frontend. It is designed for research workflows that need to connect experimental omics data, graph evidence, and an agent-style Q&A interface.

Core capabilities:

- FastAGI-backed chat proxy with blocking and streaming response support.
- Neo4j-backed graph APIs for search, node detail, neighbor expansion, relationship queries, path checks, and graph mutation.
- Multi-omics Excel analysis for transcriptomics, proteomics, metabolomics, lipidomics, and other tabular omics outputs.
- Dataset management scaffold backed by PostgreSQL, with browser local fallback in the frontend.
- Enterprise-style workbench UI for chat, graph exploration, and experiment dataset analysis.

## Project Layout

```text
Multiomics_GraphRAG_Agent_Platform/
  backend/             FastAPI service, Neo4j/PostgreSQL clients, analysis services, tests
  frontend/            Vue 3 + Vite workbench frontend
  logs/                Local runtime logs, ignored by Git
  .gitignore           Root ignore rules for secrets, caches, logs, builds, and dependencies
  README.md            Project overview and setup guide
```

## Backend

The backend lives in `backend/`.

Main modules:

- `app/api/routes/agent.py`: FastAGI chat proxy and streaming endpoint.
- `app/api/routes/graph.py`: Neo4j graph search, detail, neighbor, relationship, and path APIs.
- `app/api/routes/omics_stats.py`: Excel upload and URL-based omics analysis APIs.
- `app/api/routes/datasets.py`: Experiment dataset persistence APIs.
- `app/core/config.py`: TOML and `MOGAP_` environment-based configuration.
- `app/services/omics_stats/`: Excel parsing, statistics, ranking, and summaries.
- `db/migrations/`: PostgreSQL migration SQL.

Local setup:

```powershell
cd backend
python -m pip install -e .[dev]
Copy-Item .\config\settings.example.toml .\config\settings.toml
uvicorn app.main:app --reload --host 0.0.0.0 --port 18020
```

Run backend tests:

```powershell
cd backend
pytest
```

## Frontend

The frontend lives in `frontend/`.

Local setup:

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api` to `http://localhost:18020` by default. Override the proxy target with `VITE_API_PROXY_TARGET`.

## Configuration

Use `backend/config/settings.example.toml` as the committed template. Copy it to `backend/config/settings.toml` for local development and fill in local service credentials.

Important environment variables:

- `MOGAP_CONFIG`
- `MOGAP_POSTGRES_URL`
- `MOGAP_NEO4J_URI`
- `MOGAP_NEO4J_USER`
- `MOGAP_NEO4J_PASSWORD`
- `MOGAP_EMBEDDING_ENABLED`
- `MOGAP_EMBEDDING_BASE_URL`
- `MOGAP_EMBEDDING_API_KEY`
- `MOGAP_FASTAGI_APP_ID`
- `MOGAP_FASTAGI_SECRET_KEY`
- `MOGAP_FASTAGI_AGENT_ID`
- `MOGAP_FASTAGI_APP_USER`

## API Surface

Default API prefix: `/api/v1`.

Key endpoints:

```text
GET  /api/v1/health
POST /api/v1/agent/chat
POST /api/v1/agent/chat/stream
GET  /api/v1/graph/health
GET  /api/v1/graph/overview
POST /api/v1/graph/nodes/search
POST /api/v1/graph/nodes/detail
POST /api/v1/graph/nodes/create
POST /api/v1/graph/nodes/update
POST /api/v1/graph/nodes/delete
POST /api/v1/graph/relationships/create
POST /api/v1/graph/relationships/connected
POST /api/v1/graph/neighbors
POST /api/v1/graph/paths
POST /api/v1/omics-stats/analyze
POST /api/v1/omics-stats/analyze-url
GET  /api/v1/datasets
POST /api/v1/datasets
PATCH /api/v1/datasets/{dataset_id}
DELETE /api/v1/datasets/{dataset_id}
```

## Git Hygiene

Do not commit local secrets or generated runtime output.

Ignored by default:

- `backend/config/settings.toml`
- `.env` and `.env.*`
- `logs/` and `*.log`
- `frontend/node_modules/`
- `frontend/dist/`
- Python caches and test caches
- Local databases, uploads, temp files, certificates, and private keys

Commit only templates such as `backend/config/settings.example.toml`.

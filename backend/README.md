# Multiomics GraphRAG Agent Platform Backend

FastAPI backend for the web-based intelligent agent management platform.

## Migrated Capabilities

- Knowledge graph APIs backed by Neo4j: overview, exact/vector node search, node detail, neighbor expansion, relationship queries, path checks, node/relationship creation and node updates.
- Experimental data parsing and statistics APIs: `.xlsx` upload or URL analysis, group parsing, pairwise comparisons, p-value adjustment, ranked top features, and LLM-ready summary text.
- FastAGI agent chat proxy: signed OpenAPI requests with blocking output by default and a streaming endpoint for SSE clients.

## Layout

```text
backend/
  app/
    api/routes/          # FastAPI route modules
    core/                # configuration and infrastructure clients
    repositories/        # Neo4j query repository
    schemas/             # Pydantic models
    services/            # graph and omics analysis services
  config/
    settings.example.toml
  tests/
```

## Configuration

Copy `config/settings.example.toml` to `config/settings.toml` for local development, then fill in Neo4j, PostgreSQL, embedding, and rerank settings.

Environment variables use the `MOGAP_` prefix and override TOML values, for example:

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

## Run

```powershell
python -m pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 18020
```

## Main APIs

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
```

## Test

```powershell
pytest
```

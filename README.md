# Multiomics GraphRAG Agent Platform

Web-based intelligent agent management platform for biomedical multi-omics analysis, knowledge graph exploration, and GraphRAG-assisted Q&A.

## Project Layout

```text
Multiomics_GraphRAG_Agent_Platform/
  项目需求说明.docx
  backend/    # FastAPI, Neo4j graph APIs, omics Excel parsing/statistics, PostgreSQL scaffold
  frontend/   # Vue3 + JavaScript + CSS workbench frontend
```

## Backend

The backend is migrated from the existing omics services implementation:

- `app/api/routes/graph.py` exposes Neo4j-backed graph search, detail, neighbor, relationship, and path APIs.
- `app/api/routes/omics_stats.py` exposes Excel upload/URL analysis for experimental omics data.
- `app/core/postgres.py` and `postgres_url` configuration prepare PostgreSQL persistence for datasets, sessions, and agent management data.

## Frontend

The frontend is a Vue3 Vite app with an enterprise research workbench layout for:

- Chat agent workspace
- Dataset asset center
- Knowledge graph search and evidence preview

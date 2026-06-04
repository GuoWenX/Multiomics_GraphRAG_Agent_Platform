from __future__ import annotations

from fastapi import APIRouter

from .routes.agent import router as agent_router
from .routes.datasets import router as datasets_router
from .routes.graph import router as graph_router
from .routes.health import router as health_router
from .routes.omics_stats import router as omics_stats_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(agent_router, prefix="/agent", tags=["agent"])
api_router.include_router(datasets_router, prefix="/datasets", tags=["datasets"])
api_router.include_router(graph_router, prefix="/graph", tags=["graph"])
api_router.include_router(omics_stats_router, prefix="/omics-stats", tags=["omics-stats"])

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.graph import (
    GraphLLMTextResponse,
    GraphOverviewResponse,
    GraphQueryResponse,
    NeighborQueryRequest,
    NodeCreateRequest,
    NodeCreateResponse,
    NodeDeleteRequest,
    NodeDeleteResponse,
    NodeDetailRequest,
    NodeSearchRequest,
    NodeUpdateRequest,
    NodeUpdateResponse,
    PathQueryRequest,
    RelationshipCreateRequest,
    RelationshipCreateResponse,
    RelationshipQueryRequest,
)
from app.services.embedding_client import EmbeddingClientError
from app.services.graph_service import GraphService

router = APIRouter()


def get_graph_service() -> GraphService:
    return GraphService()


@router.get("/health")
def health(service: GraphService = Depends(get_graph_service)) -> dict[str, str]:
    try:
        service.check_health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}") from exc
    return {"status": "ok"}


@router.get("/overview", response_model=GraphOverviewResponse)
def overview(service: GraphService = Depends(get_graph_service)) -> GraphOverviewResponse:
    return service.get_overview()


@router.post("/nodes/search", response_model=GraphLLMTextResponse | GraphQueryResponse)
def search_nodes(
    payload: NodeSearchRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphLLMTextResponse | GraphQueryResponse:
    try:
        return service.search_exact_node(payload)
    except EmbeddingClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/nodes/detail", response_model=GraphQueryResponse)
def node_detail(
    payload: NodeDetailRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphQueryResponse:
    return service.get_exact_node_detail(payload)


@router.post("/nodes/create", response_model=NodeCreateResponse)
def create_node(
    payload: NodeCreateRequest,
    service: GraphService = Depends(get_graph_service),
) -> NodeCreateResponse:
    try:
        return service.create_node(payload)
    except EmbeddingClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/nodes/update", response_model=NodeUpdateResponse)
def update_node(
    payload: NodeUpdateRequest,
    service: GraphService = Depends(get_graph_service),
) -> NodeUpdateResponse:
    try:
        return service.update_node(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/nodes/delete", response_model=NodeDeleteResponse)
def delete_node(
    payload: NodeDeleteRequest,
    service: GraphService = Depends(get_graph_service),
) -> NodeDeleteResponse:
    try:
        return service.delete_node(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/relationships/create", response_model=RelationshipCreateResponse)
def create_relationship(
    payload: RelationshipCreateRequest,
    service: GraphService = Depends(get_graph_service),
) -> RelationshipCreateResponse:
    try:
        return service.create_relationship(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmbeddingClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/neighbors", response_model=GraphQueryResponse)
def neighbors(
    payload: NeighborQueryRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphQueryResponse:
    return service.get_neighbors(payload)


@router.post("/relationships/connected", response_model=GraphQueryResponse)
def connected_by_relationship(
    payload: RelationshipQueryRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphQueryResponse:
    return service.get_related_by_relationship(payload)


@router.post("/paths", response_model=GraphQueryResponse)
def direct_relationship_or_neighborhood(
    payload: PathQueryRequest,
    service: GraphService = Depends(get_graph_service),
) -> GraphQueryResponse:
    return service.check_direct_relationship_or_neighborhood(payload)

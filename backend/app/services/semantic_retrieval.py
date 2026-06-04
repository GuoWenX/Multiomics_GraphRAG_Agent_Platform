from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class EmbeddingConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str | None
    api_key: str
    dimensions: int
    batch_size: int
    timeout_seconds: float
    node_index: str
    node_property: str
    relationship_property: str


@dataclass(frozen=True)
class RerankConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str | None
    api_key: str
    top_n: int
    timeout_seconds: float


@dataclass(frozen=True)
class SemanticRetrievalConfig:
    embedding: EmbeddingConfig
    rerank: RerankConfig


def load_semantic_retrieval_config(settings: Settings | None = None) -> SemanticRetrievalConfig:
    settings = settings or get_settings()
    return SemanticRetrievalConfig(
        embedding=EmbeddingConfig(
            enabled=settings.embedding_enabled,
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
            node_index=settings.neo4j_node_embedding_index,
            node_property=settings.neo4j_node_embedding_property,
            relationship_property=settings.neo4j_relationship_embedding_property,
        ),
        rerank=RerankConfig(
            enabled=settings.rerank_enabled,
            provider=settings.rerank_provider,
            model=settings.rerank_model,
            base_url=settings.rerank_base_url,
            api_key=settings.rerank_api_key,
            top_n=settings.rerank_top_n,
            timeout_seconds=settings.rerank_timeout_seconds,
        ),
    )

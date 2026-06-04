from __future__ import annotations

from app.core.config import Settings
from app.services.semantic_retrieval import load_semantic_retrieval_config


def test_semantic_retrieval_config_loads_defaults() -> None:
    config = load_semantic_retrieval_config(Settings())

    assert config.embedding.enabled is False
    assert config.embedding.provider == "openai"
    assert config.embedding.model == "text-embedding-3-small"
    assert config.embedding.dimensions == 1536
    assert config.embedding.node_index == "kg_node_embedding_index"
    assert config.embedding.relationship_property == "embedding"
    assert config.rerank.enabled is False
    assert config.rerank.provider == "none"


def test_semantic_retrieval_config_loads_settings_values() -> None:
    settings = Settings(
        embedding_enabled=True,
        embedding_provider="openai-compatible",
        embedding_model="bge-m3",
        embedding_base_url="http://embedding.local/v1",
        embedding_api_key="embedding-key",
        embedding_dimensions=1024,
        embedding_batch_size=32,
        embedding_timeout_seconds=15.0,
        neo4j_node_embedding_index="custom_index",
        neo4j_node_embedding_property="custom_embedding",
        neo4j_relationship_embedding_property="custom_relationship_embedding",
        rerank_enabled=True,
        rerank_provider="jina",
        rerank_model="jina-reranker-v2-base-multilingual",
        rerank_base_url="http://rerank.local/v1",
        rerank_api_key="rerank-key",
        rerank_top_n=5,
        rerank_timeout_seconds=10.0,
    )

    config = load_semantic_retrieval_config(settings)

    assert config.embedding.enabled is True
    assert config.embedding.provider == "openai-compatible"
    assert config.embedding.model == "bge-m3"
    assert config.embedding.base_url == "http://embedding.local/v1"
    assert config.embedding.api_key == "embedding-key"
    assert config.embedding.dimensions == 1024
    assert config.embedding.batch_size == 32
    assert config.embedding.timeout_seconds == 15.0
    assert config.embedding.node_index == "custom_index"
    assert config.embedding.node_property == "custom_embedding"
    assert config.embedding.relationship_property == "custom_relationship_embedding"
    assert config.rerank.enabled is True
    assert config.rerank.provider == "jina"
    assert config.rerank.model == "jina-reranker-v2-base-multilingual"
    assert config.rerank.base_url == "http://rerank.local/v1"
    assert config.rerank.api_key == "rerank-key"
    assert config.rerank.top_n == 5
    assert config.rerank.timeout_seconds == 10.0

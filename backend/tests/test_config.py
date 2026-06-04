from __future__ import annotations

from app.core.config import get_settings


def test_get_settings_loads_embedding_and_rerank_from_toml(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        """
[embedding]
enabled = true
provider = "openai-compatible"
model = "bge-m3"
base_url = "http://embedding.local/v1"
api_key = "embedding-key"
dimensions = 1024
batch_size = 16
timeout_seconds = 12.5

[neo4j]
node_embedding_index = "node_vec"
node_embedding_property = "text_embedding"
relationship_embedding_property = "relationship_embedding"

[rerank]
enabled = true
provider = "jina"
model = "jina-reranker-v2-base-multilingual"
base_url = "http://rerank.local/v1"
api_key = "rerank-key"
top_n = 7
timeout_seconds = 9.5
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MOGAP_CONFIG", str(config_path))
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.embedding_enabled is True
    assert settings.embedding_provider == "openai-compatible"
    assert settings.embedding_model == "bge-m3"
    assert settings.embedding_base_url == "http://embedding.local/v1"
    assert settings.embedding_api_key == "embedding-key"
    assert settings.embedding_dimensions == 1024
    assert settings.embedding_batch_size == 16
    assert settings.embedding_timeout_seconds == 12.5
    assert settings.neo4j_node_embedding_index == "node_vec"
    assert settings.neo4j_node_embedding_property == "text_embedding"
    assert settings.neo4j_relationship_embedding_property == "relationship_embedding"
    assert settings.rerank_enabled is True
    assert settings.rerank_provider == "jina"
    assert settings.rerank_model == "jina-reranker-v2-base-multilingual"
    assert settings.rerank_top_n == 7
    assert settings.rerank_timeout_seconds == 9.5


def test_get_settings_allows_embedding_env_overrides(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "settings.toml"
    config_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("MOGAP_CONFIG", str(config_path))
    monkeypatch.setenv("MOGAP_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("MOGAP_EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("MOGAP_EMBEDDING_DIMENSIONS", "3072")
    monkeypatch.setenv("MOGAP_RERANK_ENABLED", "true")
    monkeypatch.setenv("MOGAP_RERANK_TOP_N", "3")
    get_settings.cache_clear()

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.embedding_enabled is True
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dimensions == 3072
    assert settings.rerank_enabled is True
    assert settings.rerank_top_n == 3

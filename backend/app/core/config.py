from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config" / "settings.toml"


class Settings(BaseModel):
    app_name: str = "Multiomics GraphRAG Agent Platform"
    version: str = "0.1.0"
    environment: str = "local"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/multiomics_graphrag"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str | None = None
    embedding_enabled: bool = False
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str | None = None
    embedding_api_key: str = ""
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    embedding_timeout_seconds: float = 60.0
    neo4j_node_embedding_index: str = "kg_node_embedding_index"
    neo4j_node_embedding_property: str = "embedding"
    neo4j_relationship_embedding_property: str = "embedding"
    rerank_enabled: bool = False
    rerank_provider: str = "none"
    rerank_model: str = ""
    rerank_base_url: str | None = None
    rerank_api_key: str = ""
    rerank_top_n: int = 20
    rerank_timeout_seconds: float = 60.0
    fastagi_base_url: str = "https://deepexios.deepexi.com"
    fastagi_chat_endpoint: str = "/api/openapi/chat/chat-messages"
    fastagi_app_id: str = ""
    fastagi_secret_key: str = ""
    fastagi_agent_id: str = ""
    fastagi_app_user: str = "nfyy"
    fastagi_provider: str = "credentials"
    fastagi_default_response_mode: str = "blocking"
    fastagi_timeout_seconds: float = 900.0


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _apply_env_overrides(values: dict[str, Any]) -> dict[str, Any]:
    env_map = {
        "MOGAP_APP_NAME": ("app_name", str),
        "MOGAP_VERSION": ("version", str),
        "MOGAP_ENVIRONMENT": ("environment", str),
        "MOGAP_DEBUG": ("debug", _parse_bool),
        "MOGAP_API_PREFIX": ("api_prefix", str),
        "MOGAP_CORS_ORIGINS": ("cors_origins", _parse_list),
        "MOGAP_POSTGRES_URL": ("postgres_url", str),
        "MOGAP_NEO4J_URI": ("neo4j_uri", str),
        "MOGAP_NEO4J_USER": ("neo4j_user", str),
        "MOGAP_NEO4J_PASSWORD": ("neo4j_password", str),
        "MOGAP_NEO4J_DATABASE": ("neo4j_database", str),
        "MOGAP_EMBEDDING_ENABLED": ("embedding_enabled", _parse_bool),
        "MOGAP_EMBEDDING_PROVIDER": ("embedding_provider", str),
        "MOGAP_EMBEDDING_MODEL": ("embedding_model", str),
        "MOGAP_EMBEDDING_BASE_URL": ("embedding_base_url", str),
        "MOGAP_EMBEDDING_API_KEY": ("embedding_api_key", str),
        "MOGAP_EMBEDDING_DIMENSIONS": ("embedding_dimensions", int),
        "MOGAP_EMBEDDING_BATCH_SIZE": ("embedding_batch_size", int),
        "MOGAP_EMBEDDING_TIMEOUT_SECONDS": ("embedding_timeout_seconds", float),
        "MOGAP_NEO4J_NODE_EMBEDDING_INDEX": ("neo4j_node_embedding_index", str),
        "MOGAP_NEO4J_NODE_EMBEDDING_PROPERTY": ("neo4j_node_embedding_property", str),
        "MOGAP_NEO4J_RELATIONSHIP_EMBEDDING_PROPERTY": ("neo4j_relationship_embedding_property", str),
        "MOGAP_RERANK_ENABLED": ("rerank_enabled", _parse_bool),
        "MOGAP_RERANK_PROVIDER": ("rerank_provider", str),
        "MOGAP_RERANK_MODEL": ("rerank_model", str),
        "MOGAP_RERANK_BASE_URL": ("rerank_base_url", str),
        "MOGAP_RERANK_API_KEY": ("rerank_api_key", str),
        "MOGAP_RERANK_TOP_N": ("rerank_top_n", int),
        "MOGAP_RERANK_TIMEOUT_SECONDS": ("rerank_timeout_seconds", float),
        "MOGAP_FASTAGI_BASE_URL": ("fastagi_base_url", str),
        "MOGAP_FASTAGI_CHAT_ENDPOINT": ("fastagi_chat_endpoint", str),
        "MOGAP_FASTAGI_APP_ID": ("fastagi_app_id", str),
        "MOGAP_FASTAGI_SECRET_KEY": ("fastagi_secret_key", str),
        "MOGAP_FASTAGI_AGENT_ID": ("fastagi_agent_id", str),
        "MOGAP_FASTAGI_APP_USER": ("fastagi_app_user", str),
        "MOGAP_FASTAGI_PROVIDER": ("fastagi_provider", str),
        "MOGAP_FASTAGI_DEFAULT_RESPONSE_MODE": ("fastagi_default_response_mode", str),
        "MOGAP_FASTAGI_TIMEOUT_SECONDS": ("fastagi_timeout_seconds", float),
    }
    for env_name, (setting_name, parser) in env_map.items():
        raw_value = os.getenv(env_name)
        if raw_value is not None:
            values[setting_name] = parser(raw_value)
    return values


@lru_cache
def get_settings() -> Settings:
    config_path = Path(os.getenv("MOGAP_CONFIG", DEFAULT_CONFIG_PATH))
    config = _read_toml(config_path)
    app_config = dict(config.get("app", {}))
    postgres_config = dict(config.get("postgres", {}))
    neo4j_config = dict(config.get("neo4j", {}))
    embedding_config = dict(config.get("embedding", {}))
    rerank_config = dict(config.get("rerank", {}))
    fastagi_config = dict(config.get("fastagi", {}))
    values = {
        **app_config,
        "postgres_url": postgres_config.get(
            "url",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/multiomics_graphrag",
        ),
        "neo4j_uri": neo4j_config.get("uri", "bolt://localhost:7687"),
        "neo4j_user": neo4j_config.get("user", "neo4j"),
        "neo4j_password": neo4j_config.get("password", ""),
        "neo4j_database": neo4j_config.get("database") or None,
        "neo4j_node_embedding_index": neo4j_config.get("node_embedding_index", "kg_node_embedding_index"),
        "neo4j_node_embedding_property": neo4j_config.get("node_embedding_property", "embedding"),
        "neo4j_relationship_embedding_property": neo4j_config.get("relationship_embedding_property", "embedding"),
        "embedding_enabled": embedding_config.get("enabled", False),
        "embedding_provider": embedding_config.get("provider", "openai"),
        "embedding_model": embedding_config.get("model", "text-embedding-3-small"),
        "embedding_base_url": embedding_config.get("base_url") or None,
        "embedding_api_key": embedding_config.get("api_key", ""),
        "embedding_dimensions": embedding_config.get("dimensions", 1536),
        "embedding_batch_size": embedding_config.get("batch_size", 100),
        "embedding_timeout_seconds": embedding_config.get("timeout_seconds", 60.0),
        "rerank_enabled": rerank_config.get("enabled", False),
        "rerank_provider": rerank_config.get("provider", "none"),
        "rerank_model": rerank_config.get("model", ""),
        "rerank_base_url": rerank_config.get("base_url") or None,
        "rerank_api_key": rerank_config.get("api_key", ""),
        "rerank_top_n": rerank_config.get("top_n", 20),
        "rerank_timeout_seconds": rerank_config.get("timeout_seconds", 60.0),
        "fastagi_base_url": fastagi_config.get("base_url", "https://deepexios.deepexi.com"),
        "fastagi_chat_endpoint": fastagi_config.get("chat_endpoint", "/api/openapi/chat/chat-messages"),
        "fastagi_app_id": fastagi_config.get("app_id", ""),
        "fastagi_secret_key": fastagi_config.get("secret_key", ""),
        "fastagi_agent_id": fastagi_config.get("agent_id", ""),
        "fastagi_app_user": fastagi_config.get("app_user", "nfyy"),
        "fastagi_provider": fastagi_config.get("provider", "credentials"),
        "fastagi_default_response_mode": fastagi_config.get("default_response_mode", "blocking"),
        "fastagi_timeout_seconds": fastagi_config.get("timeout_seconds", 900.0),
    }
    return Settings.model_validate(_apply_env_overrides(values))

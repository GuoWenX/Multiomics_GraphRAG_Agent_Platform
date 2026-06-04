from __future__ import annotations

import json
import time
from typing import Protocol

import requests

from app.services.semantic_retrieval import EmbeddingConfig, load_semantic_retrieval_config


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float] | None:
        ...


class EmbeddingClientError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or load_semantic_retrieval_config().embedding

    def embed_text(self, text: str) -> list[float] | None:
        text = text.strip()
        if not self.config.enabled or not text:
            return None
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        texts = [text.strip() for text in texts if text.strip()]
        if not self.config.enabled or not texts:
            return []
        if not self.config.api_key:
            raise EmbeddingClientError("Embedding API key is not configured")
        if not self.config.base_url:
            raise EmbeddingClientError("Embedding base_url is not configured")

        last_error: requests.RequestException | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    embedding_endpoint(self.config.base_url),
                    headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                    json={"model": self.config.model, "input": texts},
                    timeout=self.config.timeout_seconds,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        else:
            raise EmbeddingClientError(f"Embedding request failed: {last_error}") from last_error

        if not response.ok:
            raise EmbeddingClientError(
                f"Embedding request failed with HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
            vectors = [item["embedding"] for item in sorted(data["data"], key=lambda item: item.get("index", 0))]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise EmbeddingClientError("Embedding response did not contain data embeddings") from exc

        if len(vectors) != len(texts):
            raise EmbeddingClientError(f"Embedding count mismatch: expected {len(texts)}, got {len(vectors)}")
        for vector in vectors:
            if len(vector) != self.config.dimensions:
                raise EmbeddingClientError(
                    f"Embedding dimension mismatch: expected {self.config.dimensions}, got {len(vector)}"
                )
        return [[float(value) for value in vector] for vector in vectors]


def embedding_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1") or base.endswith("/v2"):
        return f"{base}/embeddings"
    return f"{base}/v1/embeddings"

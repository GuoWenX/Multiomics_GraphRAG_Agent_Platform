from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import requests

from app.services.semantic_retrieval import RerankConfig, load_semantic_retrieval_config


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class RerankProvider(Protocol):
    def rerank(self, query: str, texts: list[str], top_n: int | None = None) -> list[RerankResult]:
        ...


class RerankClientError(RuntimeError):
    pass


class RerankClient:
    def __init__(self, config: RerankConfig | None = None):
        self.config = config or load_semantic_retrieval_config().rerank

    def rerank(self, query: str, texts: list[str], top_n: int | None = None) -> list[RerankResult]:
        query = query.strip()
        texts = [text.strip() for text in texts]
        if not self.config.enabled or not query or not texts:
            return []
        if not self.config.api_key:
            raise RerankClientError("Rerank API key is not configured")
        if not self.config.base_url:
            raise RerankClientError("Rerank base_url is not configured")

        payload = {
            "model": self.config.model,
            "query": query,
            "texts": texts,
            "top_n": top_n or self.config.top_n,
        }

        last_error: requests.RequestException | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    rerank_endpoint(self.config.base_url),
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1 + attempt)
        else:
            raise RerankClientError(f"Rerank request failed: {last_error}") from last_error

        if not response.ok:
            raise RerankClientError(f"Rerank request failed with HTTP {response.status_code}: {response.text[:500]}")

        try:
            data = response.json()
            items = data["data"]
            return [
                RerankResult(index=int(item["index"]), score=float(item.get("score", item.get("scores"))))
                for item in items
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RerankClientError("Rerank response did not contain indexed scores") from exc


def rerank_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/rerank"):
        return base
    if base.endswith("/v1") or base.endswith("/v2"):
        return f"{base}/rerank"
    return f"{base}/v1/rerank"

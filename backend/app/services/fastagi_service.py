from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from typing import Any

import requests

from app.core.config import Settings, get_settings
from app.schemas.agent import AgentChatRequest, AgentChatResponse


class FastAGIClientError(RuntimeError):
    pass


class FastAGIService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def chat(self, payload: AgentChatRequest) -> AgentChatResponse:
        data = self._send_streaming_chat_as_blocking(payload)
        return AgentChatResponse(
            event=data.get("event"),
            task_id=data.get("task_id"),
            message_id=data.get("message_id"),
            conversation_id=data.get("conversation_id"),
            answer=data.get("answer"),
            created_at=data.get("created_at"),
            raw=data,
        )

    def _send_streaming_chat_as_blocking(self, payload: AgentChatRequest) -> dict[str, Any]:
        final_data: dict[str, Any] = {"event": "message", "answer": ""}
        answer_chunks: list[str] = []
        raw_events: list[dict[str, Any]] = []

        with requests.post(
            self._chat_url(),
            headers=self._headers(),
            json=self._payload(payload, response_mode="streaming"),
            timeout=self.settings.fastagi_timeout_seconds,
            stream=True,
        ) as response:
            self._raise_for_error(response)
            for event in self._iter_sse_data(response):
                raw_events.append(event)
                if event.get("event") == "error":
                    raise FastAGIClientError(f"FastAGI streaming error: {event}")
                if event.get("answer"):
                    answer_chunks.append(str(event["answer"]))
                for key in ("event", "task_id", "message_id", "conversation_id", "created_at"):
                    if event.get(key) is not None:
                        final_data[key] = event[key]
                if event.get("metadata") is not None:
                    final_data["metadata"] = event["metadata"]

        final_data["event"] = final_data.get("event") or "message"
        final_data["answer"] = "".join(answer_chunks) or final_data.get("answer", "")
        final_data["stream_events"] = raw_events
        return final_data

    def stream_chat(self, payload: AgentChatRequest) -> Iterator[str]:
        with requests.post(
            self._chat_url(),
            headers=self._headers(),
            json=self._payload(payload, response_mode="streaming"),
            timeout=self.settings.fastagi_timeout_seconds,
            stream=True,
        ) as response:
            self._raise_for_error(response)
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data:") or line.startswith("event:"):
                    yield f"{line}\n"
                else:
                    yield f"data: {line}\n"
                if line.startswith("data:"):
                    yield "\n"

    def _headers(self) -> dict[str, str]:
        self._validate_config()
        timestamp = str(int(time.time() * 1000))
        signature = calculate_signature(self.settings.fastagi_app_id, self.settings.fastagi_secret_key, timestamp)
        return {
            "Content-Type": "application/json",
            "app_id": self.settings.fastagi_app_id,
            "signature": signature,
            "timestamp": timestamp,
            "app_user": self.settings.fastagi_app_user,
            "provider": self.settings.fastagi_provider,
        }

    def _payload(self, payload: AgentChatRequest, *, response_mode: str) -> dict[str, Any]:
        selected_agent_id = payload.agent_id or self.settings.fastagi_agent_id
        if not selected_agent_id:
            raise FastAGIClientError("FastAGI agent_id is not configured")

        data: dict[str, Any] = {
            "inputs": payload.inputs,
            "agent_id": selected_agent_id,
            "query": payload.query,
            "response_mode": response_mode,
        }
        optional_values = {
            "conversation_id": payload.conversation_id,
            "parent_message_id": payload.parent_message_id,
            "command": payload.command,
            "command_param": payload.command_param,
            "enable_deepresearch": payload.enable_deepresearch,
            "chat_model": payload.chat_model,
            "files": [item.model_dump(exclude_none=True) for item in payload.files],
        }
        for key, value in optional_values.items():
            if value not in (None, "", [], {}):
                data[key] = value
        return data

    def _chat_url(self) -> str:
        return f"{self.settings.fastagi_base_url.rstrip('/')}/{self.settings.fastagi_chat_endpoint.lstrip('/')}"

    def _validate_config(self) -> None:
        missing = [
            name
            for name, value in {
                "fastagi_app_id": self.settings.fastagi_app_id,
                "fastagi_secret_key": self.settings.fastagi_secret_key,
                "fastagi_agent_id": self.settings.fastagi_agent_id,
                "fastagi_app_user": self.settings.fastagi_app_user,
                "fastagi_provider": self.settings.fastagi_provider,
            }.items()
            if not value
        ]
        if missing:
            raise FastAGIClientError(f"FastAGI config missing: {', '.join(missing)}")

    @staticmethod
    def _decode_json_response(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise FastAGIClientError("FastAGI response is not valid JSON") from exc
        if not isinstance(data, dict):
            raise FastAGIClientError("FastAGI response is not a JSON object")
        return data

    @staticmethod
    def _iter_sse_data(response: requests.Response) -> Iterator[dict[str, Any]]:
        data_lines: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                if data_lines:
                    yield FastAGIService._decode_sse_data("\n".join(data_lines))
                    data_lines = []
                continue
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            yield FastAGIService._decode_sse_data("\n".join(data_lines))

    @staticmethod
    def _decode_sse_data(data: str) -> dict[str, Any]:
        try:
            value = json.loads(data)
        except json.JSONDecodeError as exc:
            raise FastAGIClientError(f"FastAGI SSE data is not valid JSON: {data[:500]}") from exc
        if not isinstance(value, dict):
            raise FastAGIClientError("FastAGI SSE data is not a JSON object")
        return value

    @staticmethod
    def _raise_for_error(response: requests.Response) -> None:
        if response.ok:
            return
        raise FastAGIClientError(f"FastAGI HTTP {response.status_code}: {response.text[:1000]}")


def calculate_signature(app_id: str, secret_key: str, timestamp: str) -> str:
    message = f"{app_id}{timestamp}"
    return hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ResponseMode = Literal["blocking", "streaming"]


class AgentFile(BaseModel):
    transfer_method: Literal["remote_url", "local_file"]
    url: str | None = None
    upload_file_id: str | None = None


class AgentChatRequest(BaseModel):
    query: str = Field(min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    response_mode: ResponseMode | None = None
    conversation_id: str | None = None
    parent_message_id: str | None = None
    command: str | None = None
    command_param: dict[str, Any] | None = None
    enable_deepresearch: str | None = None
    chat_model: str | None = None
    files: list[AgentFile] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    event: str | None = None
    task_id: str | None = None
    message_id: str | None = None
    conversation_id: str | None = None
    answer: str | None = None
    created_at: float | int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

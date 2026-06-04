from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.fastagi_service import FastAGIClientError, FastAGIService

router = APIRouter()


def get_fastagi_service() -> FastAGIService:
    return FastAGIService()


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    payload: AgentChatRequest,
    service: FastAGIService = Depends(get_fastagi_service),
) -> AgentChatResponse:
    try:
        return service.chat(payload)
    except FastAGIClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/chat/stream")
def stream_chat(
    payload: AgentChatRequest,
    service: FastAGIService = Depends(get_fastagi_service),
) -> StreamingResponse:
    def events() -> Iterator[str]:
        try:
            yield from service.stream_chat(payload)
        except FastAGIClientError as exc:
            data = json.dumps({"event": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {data}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.schemas.omics_stats import AnalyzeRequest, AnalyzeResponse, AnalyzeUrlRequest, PreviewResponse
from app.services.omics_stats_service import OmicsStatsService

router = APIRouter()


def get_omics_stats_service() -> OmicsStatsService:
    return OmicsStatsService()


@router.post("/preview", response_model=PreviewResponse)
async def preview(
    file: UploadFile = File(...),
    service: OmicsStatsService = Depends(get_omics_stats_service),
) -> PreviewResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    content = await file.read()
    return service.preview_content(content)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile = File(...),
    request: str | None = Form(default=None),
    service: OmicsStatsService = Depends(get_omics_stats_service),
) -> AnalyzeResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")
    payload = parse_analyze_request(request)
    content = await file.read()
    return service.analyze_content(content, payload)


@router.post("/analyze-url", response_model=AnalyzeResponse)
def analyze_url(
    payload: AnalyzeUrlRequest,
    service: OmicsStatsService = Depends(get_omics_stats_service),
) -> AnalyzeResponse:
    return service.analyze_url(payload)


def parse_analyze_request(request: str | None) -> AnalyzeRequest:
    if not request:
        return AnalyzeRequest()
    try:
        data = json.loads(request)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request JSON: {exc.msg}") from exc
    return AnalyzeRequest.model_validate(data)

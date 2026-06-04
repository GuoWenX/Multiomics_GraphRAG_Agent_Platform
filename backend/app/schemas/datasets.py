from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExperimentDatasetCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(default=0, ge=0)
    top_k: int = Field(default=100, ge=1, le=1000)
    group_descriptions: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    results: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentDatasetUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class ExperimentDatasetResponse(BaseModel):
    id: str
    app_user: str
    display_name: str
    file_name: str
    file_size: int
    top_k: int
    result_count: int
    group_descriptions: dict[str, str]
    warnings: list[str]
    results: list[dict[str, Any]]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

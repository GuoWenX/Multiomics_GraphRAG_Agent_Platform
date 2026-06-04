from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ComparisonRequest(BaseModel):
    reference_group: str
    test_group: str


class AnalyzeRequest(BaseModel):
    comparisons: list[ComparisonRequest] = Field(default_factory=list)
    top_n: int = Field(default=100, ge=1, le=1000)
    test_method: Literal["auto", "welch_t_test", "mannwhitney_u"] = "welch_t_test"
    p_adjust_method: Literal["fdr_bh", "bonferroni", "holm", "none"] = "fdr_bh"
    rank_by: Literal[
        "p_adjusted_then_abs_log2fc",
        "p_value_then_abs_log2fc",
        "p_adjusted",
        "p_value",
        "abs_log2fc",
        "fold_change",
        "mean_difference",
    ] = "p_adjusted_then_abs_log2fc"


class AnalyzeUrlRequest(AnalyzeRequest):
    file_url: str


class AnalyzeResponse(BaseModel):
    group_descriptions: dict[str, str]
    warnings: list[str]
    results: list[dict]

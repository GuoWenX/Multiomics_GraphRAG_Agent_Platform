from __future__ import annotations

from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.schemas.omics_stats import AnalyzeRequest, AnalyzeResponse, AnalyzeUrlRequest
from app.services.omics_stats.excel_parser import read_workbook
from app.services.omics_stats.stats_engine import Comparison, analyze_omics


class OmicsStatsService:
    def analyze_content(self, content: bytes, payload: AnalyzeRequest) -> AnalyzeResponse:
        parsed = read_workbook(content)
        comparisons = [Comparison(c.reference_group, c.test_group) for c in payload.comparisons] or None
        results, stat_warnings = analyze_omics(
            parsed.omics_data,
            comparisons=comparisons,
            top_n=payload.top_n,
            test_method=payload.test_method,
            p_adjust_method=payload.p_adjust_method,
            rank_by=payload.rank_by,
        )
        return AnalyzeResponse(
            group_descriptions=parsed.group_descriptions,
            warnings=parsed.warnings + stat_warnings,
            results=results,
        )

    def analyze_url(self, payload: AnalyzeUrlRequest) -> AnalyzeResponse:
        try:
            request = Request(payload.file_url, headers={"User-Agent": "multiomics-graphrag-agent-platform/0.1"})
            with urlopen(request, timeout=60) as response:
                content = response.read()
        except URLError as exc:
            raise HTTPException(status_code=400, detail=f"Failed to download file_url: {exc}") from exc
        if not content:
            raise HTTPException(status_code=400, detail="Downloaded file is empty")
        return self.analyze_content(content, payload)

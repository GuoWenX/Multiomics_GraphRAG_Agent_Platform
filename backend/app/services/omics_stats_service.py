from __future__ import annotations

from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException

from app.schemas.omics_stats import AnalyzeRequest, AnalyzeResponse, AnalyzeUrlRequest, PreviewResponse
from app.services.omics_stats.excel_parser import read_workbook
from app.services.omics_stats.stats_engine import Comparison, analyze_omics


class OmicsStatsService:
    def preview_content(self, content: bytes) -> PreviewResponse:
        parsed = read_workbook(content)
        sheet_groups: dict[str, set[str]] = {}
        all_groups: set[str] = set()
        sheets = []
        for omics_type, features in parsed.omics_data.items():
            groups = sorted({
                group
                for group_values in features.values()
                for group, values in group_values.items()
                if values
            })
            sheet_groups[omics_type] = set(groups)
            all_groups.update(groups)
            sheets.append({
                "name": omics_type,
                "feature_count": len(features),
                "groups": groups,
            })
        groups = sorted(parsed.group_descriptions) or sorted(all_groups)
        comparisons = [
            {
                "reference_group": reference,
                "test_group": test,
                "label": f"{test}_vs_{reference}",
            }
            for index, reference in enumerate(groups)
            for test in groups[index + 1 :]
        ]
        can_analyze = bool(sheets) and len(groups) >= 2 and any(sheet["feature_count"] > 0 for sheet in sheets)
        warnings = list(parsed.warnings)
        if not sheets:
            warnings.append("未发现可解析的组学数据工作表")
        if len(groups) < 2:
            warnings.append("至少需要 2 个实验组才能进行组间比较")
        return PreviewResponse(
            group_descriptions=parsed.group_descriptions,
            warnings=warnings,
            sheets=sheets,
            groups=groups,
            comparisons=comparisons,
            can_analyze=can_analyze,
        )

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

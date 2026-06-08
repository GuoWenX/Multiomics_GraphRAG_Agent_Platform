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
        all_groups: set[str] = set()
        sheets = []
        for omics_type, features in parsed.omics_data.items():
            groups = sorted({
                group
                for group_values in features.values()
                for group, values in group_values.items()
                if values
            })
            all_groups.update(groups)
            sheets.append({
                "name": omics_type,
                "feature_count": len(features),
                "groups": groups,
            })
        groups = sorted(all_groups)
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
        described_groups_without_samples = sorted(set(parsed.group_descriptions) - all_groups)
        for group in described_groups_without_samples:
            warnings.append(f"实验组 {group} 在实验组说明中存在，但没有匹配到样本列，已从可选比较中排除")
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
        available_groups = {
            group
            for features in parsed.omics_data.values()
            for group_values in features.values()
            for group, values in group_values.items()
            if values
        }
        requested_comparisons = [Comparison(c.reference_group, c.test_group) for c in payload.comparisons]
        invalid_comparisons = [
            comparison
            for comparison in requested_comparisons
            if comparison.reference_group not in available_groups or comparison.test_group not in available_groups
        ]
        valid_comparisons = [
            comparison
            for comparison in requested_comparisons
            if comparison.reference_group in available_groups and comparison.test_group in available_groups
        ]
        comparisons = valid_comparisons if requested_comparisons else None
        if requested_comparisons and not valid_comparisons:
            results, stat_warnings = [], []
        else:
            results, stat_warnings = analyze_omics(
                parsed.omics_data,
                comparisons=comparisons,
                top_n=payload.top_n,
                test_method=payload.test_method,
                p_adjust_method=payload.p_adjust_method,
                rank_by=payload.rank_by,
            )
        validation_warnings = [
            (
                f"已跳过无可用样本的比较 {comparison.test_group}_vs_{comparison.reference_group}；"
                "请确认两个实验组都有匹配的样本列"
            )
            for comparison in invalid_comparisons
        ]
        return AnalyzeResponse(
            group_descriptions=parsed.group_descriptions,
            warnings=parsed.warnings + validation_warnings + stat_warnings,
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

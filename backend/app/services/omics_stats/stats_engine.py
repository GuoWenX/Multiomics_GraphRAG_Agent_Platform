from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests

from .ranking import sort_results

TestMethod = Literal["auto", "welch_t_test", "mannwhitney_u"]
PAdjustMethod = Literal["fdr_bh", "bonferroni", "holm", "none"]


@dataclass(frozen=True)
class Comparison:
    reference_group: str
    test_group: str


def generate_pairwise_comparisons(groups: list[str]) -> list[Comparison]:
    return [Comparison(reference_group=a, test_group=b) for a, b in itertools.combinations(groups, 2)]


def analyze_omics(
    omics_data: dict[str, dict[str, dict[str, list[float]]]],
    comparisons: list[Comparison] | None = None,
    top_n: int = 100,
    test_method: TestMethod = "welch_t_test",
    p_adjust_method: PAdjustMethod = "fdr_bh",
    rank_by: str = "p_adjusted_then_abs_log2fc",
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    results: list[dict] = []
    for omics_type, features in omics_data.items():
        groups = _groups_for_features(features)
        active_comparisons = comparisons or generate_pairwise_comparisons(groups)
        for comparison in active_comparisons:
            rows = []
            for feature, group_values in features.items():
                ref_values = _clean_values(group_values.get(comparison.reference_group, []))
                test_values = _clean_values(group_values.get(comparison.test_group, []))
                row, row_warnings = compare_feature(
                    feature=feature,
                    reference_group=comparison.reference_group,
                    test_group=comparison.test_group,
                    reference_values=ref_values,
                    test_values=test_values,
                    test_method=test_method,
                )
                warnings.extend(f"{omics_type}/{feature}: {w}" for w in row_warnings)
                rows.append(row)
            _apply_p_adjust(rows, p_adjust_method)
            comparison_name = f"{comparison.test_group}_vs_{comparison.reference_group}"
            top_rows = sort_results(rows, rank_by=rank_by, top_n=top_n)
            results.append({
                "omics_type": omics_type,
                "comparison": comparison_name,
                "reference_group": comparison.reference_group,
                "test_group": comparison.test_group,
                "llm_text": build_llm_text(
                    omics_type=omics_type,
                    comparison=comparison_name,
                    reference_group=comparison.reference_group,
                    test_group=comparison.test_group,
                    top_rows=top_rows,
                ),
                "top": top_rows,
            })
    return results, warnings


def build_llm_text(
    omics_type: str,
    comparison: str,
    reference_group: str,
    test_group: str,
    top_rows: list[dict],
) -> str:
    if not top_rows:
        feature_text = "无可排序条目"
    else:
        entries = []
        for idx, row in enumerate(top_rows, start=1):
            entries.append(f"{idx}. {row.get('feature')}（{_direction_text(row)}）")
        feature_text = "；".join(entries)
    return (
        f"在{omics_type}中，比较{comparison}（{test_group}相对于{reference_group}）时，"
        f"TOP差异条目如下：{feature_text}。"
    )


def _direction_text(row: dict) -> str:
    log2fc = row.get("log2fc")
    mean_difference = row.get("mean_difference")
    value = log2fc if log2fc is not None else mean_difference
    if value is None:
        return "方向无法判断"
    fold_text = _fold_change_text(row.get("fold_change"))
    if value > 0:
        return f"上调{fold_text}"
    if value < 0:
        return f"下调{fold_text}"
    return "基本不变"


def _fold_change_text(fold_change: float | None) -> str:
    if fold_change is None or fold_change <= 0:
        return "，倍数无法判断"
    if fold_change >= 1:
        return f"，约{_fmt_fold(fold_change)}倍"
    return f"，约{_fmt_fold(1 / fold_change)}倍"


def _fmt_fold(value: float) -> str:
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"
def compare_feature(
    feature: str,
    reference_group: str,
    test_group: str,
    reference_values: list[float],
    test_values: list[float],
    test_method: TestMethod = "welch_t_test",
) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    ref = np.array(reference_values, dtype=float)
    test = np.array(test_values, dtype=float)
    ref_mean = _mean(ref)
    test_mean = _mean(test)
    ref_sd = _sd(ref)
    test_sd = _sd(test)
    mean_difference = _safe_diff(test_mean, ref_mean)
    fold_change = _safe_div(test_mean, ref_mean)
    log2fc = math.log2(fold_change) if fold_change is not None and fold_change > 0 else None
    p_value = None
    method = "welch_t_test" if test_method == "auto" else test_method

    if len(ref) < 2 or len(test) < 2:
        warnings.append(f"{reference_group} 或 {test_group} 有效样本数少于 2，P 值为空")
    else:
        p_value = _p_value(ref, test, method)
        if p_value is None:
            warnings.append(f"{method} 无法计算 P 值")

    return {
        "feature": feature,
        "reference_group": reference_group,
        "test_group": test_group,
        "reference_n": int(len(ref)),
        "test_n": int(len(test)),
        "reference_mean": ref_mean,
        "reference_sd": ref_sd,
        "test_mean": test_mean,
        "test_sd": test_sd,
        "mean_difference": mean_difference,
        "fold_change": fold_change,
        "log2fc": log2fc,
        "p_value": p_value,
        "p_adjusted": None,
        "test_method": method,
    }, warnings


def _p_value(ref: np.ndarray, test: np.ndarray, method: str) -> float | None:
    try:
        if method == "mannwhitney_u":
            value = stats.mannwhitneyu(ref, test, alternative="two-sided").pvalue
        else:
            value = _welch_t_test_p_value(ref, test)
    except Exception:
        return None
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _welch_t_test_p_value(ref: np.ndarray, test: np.ndarray) -> float | None:
    n_ref = len(ref)
    n_test = len(test)
    if n_ref < 2 or n_test < 2:
        return None

    mean_ref = float(np.mean(ref))
    mean_test = float(np.mean(test))
    var_ref = float(np.var(ref, ddof=1))
    var_test = float(np.var(test, ddof=1))
    if not all(math.isfinite(value) for value in (mean_ref, mean_test, var_ref, var_test)):
        return None

    ref_term = var_ref / n_ref
    test_term = var_test / n_test
    standard_error = math.sqrt(ref_term + test_term)
    if standard_error == 0:
        return 1.0 if mean_ref == mean_test else 0.0

    numerator = (ref_term + test_term) ** 2
    denominator = 0.0
    if n_ref > 1:
        denominator += (ref_term**2) / (n_ref - 1)
    if n_test > 1:
        denominator += (test_term**2) / (n_test - 1)
    if denominator == 0:
        return 1.0 if mean_ref == mean_test else 0.0

    degrees_of_freedom = numerator / denominator
    if not math.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0:
        return None

    t_stat = (mean_test - mean_ref) / standard_error
    return float(2 * stats.t.sf(abs(t_stat), degrees_of_freedom))


def _apply_p_adjust(rows: list[dict], method: PAdjustMethod) -> None:
    if method == "none":
        for row in rows:
            row["p_adjusted"] = row["p_value"]
        return
    indexed = [(idx, row["p_value"]) for idx, row in enumerate(rows) if row.get("p_value") is not None]
    if not indexed:
        return
    indices, p_values = zip(*indexed)
    adjusted = multipletests(p_values, method=method)[1]
    for idx, p_adj in zip(indices, adjusted):
        rows[idx]["p_adjusted"] = float(p_adj) if math.isfinite(float(p_adj)) else None


def _groups_for_features(features: dict[str, dict[str, list[float]]]) -> list[str]:
    groups: set[str] = set()
    for group_values in features.values():
        groups.update(group_values)
    return sorted(groups)


def _clean_values(values: list[float]) -> list[float]:
    clean = []
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            clean.append(numeric)
    return clean


def _mean(values: np.ndarray) -> float | None:
    if len(values) == 0:
        return None
    value = float(np.mean(values))
    return value if math.isfinite(value) else None


def _sd(values: np.ndarray) -> float | None:
    if len(values) < 2:
        return None
    value = float(np.std(values, ddof=1))
    return value if math.isfinite(value) else None


def _safe_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    value = a / b
    return value if math.isfinite(value) else None

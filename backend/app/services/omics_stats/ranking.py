from __future__ import annotations

from math import isfinite
from typing import Any


def sort_results(rows: list[dict[str, Any]], rank_by: str, top_n: int) -> list[dict[str, Any]]:
    key_fn = _key_for(rank_by)
    ranked = sorted(rows, key=key_fn)
    for idx, row in enumerate(ranked[:top_n], start=1):
        row["rank"] = idx
    return ranked[:top_n]


def _none_last(value: Any, reverse: bool = False) -> float:
    if value is None:
        return float("-inf") if reverse else float("inf")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("-inf") if reverse else float("inf")
    if not isfinite(numeric):
        return float("-inf") if reverse else float("inf")
    return -numeric if reverse else numeric


def _key_for(rank_by: str):
    if rank_by == "p_value":
        return lambda r: (_none_last(r.get("p_value")), _none_last(abs_value(r.get("log2fc")), reverse=True))
    if rank_by == "p_adjusted":
        return lambda r: (_none_last(r.get("p_adjusted")), _none_last(r.get("p_value")), _none_last(abs_value(r.get("log2fc")), reverse=True))
    if rank_by == "abs_log2fc":
        return lambda r: (_none_last(abs_value(r.get("log2fc")), reverse=True), _none_last(r.get("p_adjusted")), _none_last(r.get("p_value")))
    if rank_by == "fold_change":
        return lambda r: (_none_last(abs_value(r.get("fold_change")), reverse=True), _none_last(r.get("p_adjusted")))
    if rank_by == "mean_difference":
        return lambda r: (_none_last(abs_value(r.get("mean_difference")), reverse=True), _none_last(r.get("p_adjusted")))
    return lambda r: (_none_last(r.get("p_adjusted")), _none_last(r.get("p_value")), _none_last(abs_value(r.get("log2fc")), reverse=True))


def abs_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None

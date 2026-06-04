from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

INFO_SHEETS = {"00_填写说明", "01_实验组说明"}
DEFAULT_GROUPS = ["shCON_SHAM", "shSmpd3_SHAM", "shCON_POD2", "shSmpd3_POD2"]


@dataclass
class ParsedWorkbook:
    group_descriptions: dict[str, str]
    omics_data: dict[str, dict[str, dict[str, list[float]]]]
    warnings: list[str] = field(default_factory=list)


def normalize_name(text: str) -> str:
    value = str(text).strip().lower()
    value = re.sub(r"[\s\-]+", "_", value)
    value = value.replace("鼠", "mouse")
    value = re.sub(r"_?mouse_?(\d+)$", r"_mouse\1", value)
    value = re.sub(r"_?m_?(\d+)$", r"_mouse\1", value)
    value = re.sub(r"_(\d+)$", r"_mouse\1", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def group_to_pattern(group: str) -> str:
    return normalize_name(group)


def parse_sample_column(column_name: str, known_groups: list[str]) -> str | None:
    normalized_col = normalize_name(column_name)
    for group in sorted(known_groups, key=len, reverse=True):
        normalized_group = group_to_pattern(group)
        if normalized_col == normalized_group:
            return group
        if normalized_col.startswith(normalized_group + "_"):
            return group
        if normalized_group in normalized_col.split("_"):
            return group
        compact_col = normalized_col.replace("_", "")
        compact_group = normalized_group.replace("_", "")
        if compact_col.startswith(compact_group):
            return group
    return None


def read_workbook(source: str | Path | bytes | BinaryIO) -> ParsedWorkbook:
    excel_source = _coerce_source(source)
    xls = pd.ExcelFile(excel_source)
    group_descriptions = _read_group_descriptions(excel_source, xls.sheet_names)
    known_groups = list(group_descriptions) or DEFAULT_GROUPS
    omics_data: dict[str, dict[str, dict[str, list[float]]]] = {}
    warnings: list[str] = []

    for sheet_name in xls.sheet_names:
        if sheet_name in INFO_SHEETS:
            continue
        df = pd.read_excel(excel_source, sheet_name=sheet_name)
        if df.empty or len(df.columns) < 2:
            warnings.append(f"{sheet_name}: sheet 为空或没有样本列，已跳过")
            continue
        feature_col = df.columns[0]
        sample_columns: list[tuple[str, str]] = []
        for col in df.columns[1:]:
            group = parse_sample_column(str(col), known_groups)
            if group is None:
                warnings.append(f"{sheet_name}: 样本列 {col} 无法匹配到实验组，已跳过")
                continue
            sample_columns.append((str(col), group))
        feature_map: dict[str, dict[str, list[float]]] = {}
        for _, row in df.iterrows():
            feature = row.get(feature_col)
            if pd.isna(feature) or str(feature).strip() == "":
                continue
            feature_name = str(feature).strip()
            groups = feature_map.setdefault(feature_name, {})
            for col, group in sample_columns:
                value = pd.to_numeric(row.get(col), errors="coerce")
                if pd.isna(value):
                    continue
                groups.setdefault(group, []).append(float(value))
        omics_data[sheet_name] = feature_map

    return ParsedWorkbook(group_descriptions=group_descriptions, omics_data=omics_data, warnings=warnings)


def _coerce_source(source: str | Path | bytes | BinaryIO):
    if isinstance(source, bytes):
        return BytesIO(source)
    return source


def _read_group_descriptions(excel_source, sheet_names: list[str]) -> dict[str, str]:
    if "01_实验组说明" not in sheet_names:
        return {}
    df = pd.read_excel(excel_source, sheet_name="01_实验组说明")
    if df.empty or len(df.columns) < 1:
        return {}
    group_col = df.columns[0]
    desc_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
    result: dict[str, str] = {}
    for _, row in df.iterrows():
        group = row.get(group_col)
        if pd.isna(group) or str(group).strip() == "":
            continue
        desc = row.get(desc_col)
        result[str(group).strip()] = "" if pd.isna(desc) else str(desc).strip()
    return result

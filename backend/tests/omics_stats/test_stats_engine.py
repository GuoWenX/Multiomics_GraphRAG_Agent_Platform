import math

from app.services.omics_stats.stats_engine import Comparison, analyze_omics, compare_feature


def test_compare_feature_basic_metrics():
    row, warnings = compare_feature(
        feature="A",
        reference_group="control",
        test_group="treated",
        reference_values=[1, 2, 3],
        test_values=[2, 4, 6],
    )
    assert warnings == []
    assert row["reference_n"] == 3
    assert row["test_n"] == 3
    assert row["reference_mean"] == 2
    assert row["test_mean"] == 4
    assert row["fold_change"] == 2
    assert row["log2fc"] == 1
    assert row["p_value"] is not None


def test_zero_reference_mean_has_no_fc_or_log2fc():
    row, _ = compare_feature(
        feature="A",
        reference_group="control",
        test_group="treated",
        reference_values=[0, 0, 0],
        test_values=[1, 2, 3],
    )
    assert row["fold_change"] is None
    assert row["log2fc"] is None


def test_small_sample_has_no_p_value():
    row, warnings = compare_feature(
        feature="A",
        reference_group="control",
        test_group="treated",
        reference_values=[1],
        test_values=[2, 3],
    )
    assert row["p_value"] is None
    assert warnings


def test_analyze_omics_applies_adjusted_p_values_and_top_n():
    omics = {
        "AA_氨基酸组学": {
            "A": {"control": [1, 1, 1], "treated": [3, 3, 3]},
            "B": {"control": [1, 2, 3], "treated": [1, 2, 3]},
            "C": {"control": [1, 2, 3], "treated": [10, 11, 12]},
        }
    }
    results, warnings = analyze_omics(
        omics,
        comparisons=[Comparison("control", "treated")],
        top_n=2,
    )
    assert len(results) == 1
    assert len(results[0]["top"]) == 2
    assert all("p_adjusted" in row for row in results[0]["top"])
    assert "llm_text" in results[0]
    assert "TOP差异条目如下" in results[0]["llm_text"]
    assert "上调" in results[0]["llm_text"] or "下调" in results[0]["llm_text"]
    assert "约" in results[0]["llm_text"]
    assert "倍" in results[0]["llm_text"]
    assert "A" in results[0]["llm_text"] or "C" in results[0]["llm_text"]

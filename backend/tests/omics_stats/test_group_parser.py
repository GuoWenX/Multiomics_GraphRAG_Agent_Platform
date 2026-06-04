from app.services.omics_stats.excel_parser import normalize_name, parse_sample_column


def test_parse_chinese_mouse_columns_with_variable_counts():
    groups = ["shCON_SHAM", "shSmpd3_SHAM", "shCON_POD2", "shSmpd3_POD2"]
    assert parse_sample_column("shCON_SHAM_鼠1", groups) == "shCON_SHAM"
    assert parse_sample_column("shCON_SHAM_鼠5", groups) == "shCON_SHAM"
    assert parse_sample_column("shSmpd3_POD2_鼠3", groups) == "shSmpd3_POD2"


def test_parse_column_name_variants():
    groups = ["shCON_SHAM", "shSmpd3_POD2"]
    assert parse_sample_column("shCON SHAM 1", groups) == "shCON_SHAM"
    assert parse_sample_column("shCON-SHAM-mouse2", groups) == "shCON_SHAM"
    assert parse_sample_column("shSmpd3 POD2 m4", groups) == "shSmpd3_POD2"


def test_longest_group_match_wins():
    groups = ["shCON", "shCON_POD2"]
    assert parse_sample_column("shCON_POD2_鼠1", groups) == "shCON_POD2"


def test_normalize_name():
    assert normalize_name("shCON SHAM 鼠1") == "shcon_sham_mouse1"

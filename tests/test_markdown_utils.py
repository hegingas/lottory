"""markdown_utils 烟雾测试：格式化函数和 Markdown 辅助工具。"""


from lottery.markdown_utils import (
    _dlt_appendix_five_singles_line,
    _fmt2,
    _pattern_weight_md_line,
    _prediction_md_appendix_budget_rules,
    _prediction_md_appendix_kl8_bet,
    _ssq_appendix_five_singles_line,
    now_cn_iso,
)


def test_fmt2():
    assert _fmt2(1) == "01"
    assert _fmt2(9) == "09"
    assert _fmt2(10) == "10"
    assert _fmt2(35) == "35"


def test_now_cn_iso():
    ts = now_cn_iso()
    assert "+08:00" in ts


def test_pattern_weight_md_line():
    line = _pattern_weight_md_line()
    assert "×" in line or "%" in line  # returns weight formula like "18%×当前遗漏 + ..."
    assert isinstance(line, str)


def test_prediction_md_appendix_budget_rules():
    result = _prediction_md_appendix_budget_rules("大乐透", "前区 01 05 10 15 20 + 后区 01 06")
    assert "10" in result or "30" in result
    assert "元" in result


def test_prediction_md_appendix_kl8_bet():
    result = _prediction_md_appendix_kl8_bet("01 02 03 04 05 06 07 08 09 10 11")
    assert "选十" in result
    assert "元" in result


def test_dlt_appendix_five_singles_line():
    line = _dlt_appendix_five_singles_line()
    assert "10 元" in line or "10" in line
    assert isinstance(line, str)


def test_ssq_appendix_five_singles_line():
    line = _ssq_appendix_five_singles_line()
    assert "10 元" in line or "10" in line
    assert isinstance(line, str)


def test_now_cn_iso_format():
    ts = now_cn_iso()
    assert len(ts) > 10
    assert "T" in ts  # ISO format has T separator

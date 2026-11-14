"""算法 A（薪资口径归一）单测：正常 / 边界 / 不可比 / 矛盾 / 确定性。"""
from __future__ import annotations

import pytest

from src.services.salary_norm import parse_many, parse_salary


def test_range_with_13_months():
    result = parse_salary("8-12K·13薪")
    assert result["status"] == "parsed"
    assert result["months"] == 13
    assert (result["salary_low"], result["salary_high"]) == (8000, 12000)
    # 8000×12/13=7385、12000×12/13=11077、10000×12/13=9231
    assert result["monthly_low"] == 7385
    assert result["monthly_high"] == 11077
    assert result["monthly_median"] == 9231
    assert "13 薪" in result["norm_basis"]


def test_annual_salary_converted_to_monthly():
    result = parse_salary("年薪18万")
    assert result["status"] == "parsed"
    assert result["annual_total"] == 180000
    assert result["monthly_median"] == 15000
    assert result["months"] == 12


def test_yuan_per_month_and_fullwidth_variants():
    assert parse_salary("4000-6000元/月")["monthly_median"] == 5000
    fullwidth = parse_salary("２万－３万/月")
    assert (fullwidth["monthly_low"], fullwidth["monthly_high"]) == (20000, 30000)
    assert parse_salary("６千-９千/月")["monthly_median"] == 7500


def test_negotiable_has_null_median_and_low_confidence():
    result = parse_salary("面议")
    assert result["status"] == "negotiable"
    assert result["monthly_median"] is None
    assert result["confidence"] == pytest.approx(0.2)


def test_contradiction_is_unparsed():
    result = parse_salary("12-8K")
    assert result["status"] == "unparsed"
    assert "矛盾" in result["reason"]
    assert result["monthly_median"] is None


def test_implausible_magnitude_is_unparsed():
    assert parse_salary("100元/天")["status"] == "unparsed"
    assert parse_salary("")["status"] == "unparsed"


def test_batch_stats_and_unparsed_list():
    batch = parse_many(["8-12K·13薪", "面议", "12-8K", "年薪18万", "没有金额"])
    assert batch["stats"]["total"] == 5
    assert batch["stats"]["parsed"] == 2
    assert batch["stats"]["negotiable"] == 1
    assert batch["stats"]["unparsed"] == 2
    assert batch["stats"]["fail_rate"] == pytest.approx(0.4)
    assert [item["index"] for item in batch["unparsed"]] == [2, 4]


def test_deterministic():
    raws = ["8-12K·13薪", "年薪18万", "面议", "15-25K·14薪"]
    assert parse_many(raws) == parse_many(raws)

"""归一解析（业务模块②）：公司名、职位词干、城市、学历/经验、薪资口径。

薪资口径调用算法 A（services/salary_norm.py），本模块只负责把一条原始岗位
补齐成「可比较、可分块」的规范化字段，seed 与归并运行共用同一条代码路径。
"""
from __future__ import annotations

import re
import unicodedata

from src.constants.enums import DEGREE_LABELS, EXPERIENCE_LABELS, Degree, Experience
from src.services import salary_norm

COMPANY_BRACKET = re.compile(r"[（(][^）)]{0,24}[）)]")
COMPANY_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "分公司",
    "集团",
    "公司",
)

TITLE_BRACKET = re.compile(r"[（(][^）)]{0,24}[）)]")
TITLE_NOISE = (
    "急聘", "诚聘", "高薪", "招聘", "直招", "内推", "双休", "五险一金", "包吃住",
    "包住", "包吃", "长期有效", "岗位", "职位", "急招", "校招", "社招",
)
TITLE_SPLIT = re.compile(r"[\s\-—_/·,，、。;；:：!！?？\"'“”‘’|]+")

CITY_SUFFIX = re.compile(r"(特别行政区|自治区|省|市)$")

DEGREE_ALIASES: dict[str, str] = {
    "不限": Degree.ANY.value,
    "学历不限": Degree.ANY.value,
    "大专": Degree.COLLEGE.value,
    "专科": Degree.COLLEGE.value,
    "本科": Degree.BACHELOR.value,
    "统招本科": Degree.BACHELOR.value,
    "硕士": Degree.MASTER.value,
    "研究生": Degree.MASTER.value,
    "博士": Degree.DOCTOR.value,
}

EXPERIENCE_ALIASES: dict[str, str] = {
    "不限": Experience.ANY.value,
    "经验不限": Experience.ANY.value,
    "1-3年": Experience.JUNIOR.value,
    "1-3 年": Experience.JUNIOR.value,
    "3-5年": Experience.MIDDLE.value,
    "3-5 年": Experience.MIDDLE.value,
    "5-10年": Experience.SENIOR.value,
    "5-10 年": Experience.SENIOR.value,
    "10年以上": Experience.EXPERT.value,
    "10 年以上": Experience.EXPERT.value,
}


def _nfkc(raw: str | None) -> str:
    return unicodedata.normalize("NFKC", raw or "").strip()


def normalize_company(raw: str | None) -> str:
    """公司名归一：去括号地域标注、去法人后缀、去空白、转小写。"""
    text = _nfkc(raw)
    text = re.sub(r"\s+", "", text)
    text = COMPANY_BRACKET.sub("", text)
    for suffix in COMPANY_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    return text.lower()


def normalize_title(raw: str | None) -> str:
    """职位词干：去括号补充、去招聘噪声词、去标点空格、转小写。"""
    text = _nfkc(raw).lower()
    text = TITLE_BRACKET.sub("", text)
    for token in TITLE_NOISE:
        text = text.replace(token, "")
    text = TITLE_SPLIT.sub("", text)
    return text


def normalize_city(raw: str | None) -> str:
    text = _nfkc(raw)
    text = text.split("·")[0].split(",")[0].strip()
    text = CITY_SUFFIX.sub("", text)
    return text or "未知"


def normalize_degree(raw: str | None) -> str:
    text = _nfkc(raw)
    return DEGREE_ALIASES.get(text, Degree.ANY.value)


def normalize_experience(raw: str | None) -> str:
    text = _nfkc(raw)
    return EXPERIENCE_ALIASES.get(text, Experience.ANY.value)


def title_tokens(title_stem: str) -> set[str]:
    """字符级 token（中文不分词，拉丁字母按连续串）。

    已知简化：字符集合的 Jaccard 会把「后端开发」和「前端开发」判得偏高，
    但对「Java开发工程师 / Java 开发工程师（后端）」这类噪声差异有效，
    阈值 0.82 下不会把不同职能混为一簇（见 backend/tests/test_dedupe.py）。
    """
    tokens: set[str] = set()
    for chunk in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", title_stem):
        tokens.add(chunk)
    return tokens


def job_family(stem: str) -> str:
    """粗粒度职能族：用于人工复核页展示，不参与相似度计算。"""
    for marker in ("java", "前端", "后端", "测试", "运维", "算法", "产品", "运营", "销售", "设计", "数据"):
        if marker in stem:
            return marker
    return "其他"


def enrich_post_fields(
    *,
    company_raw: str,
    title_raw: str,
    city: str,
    salary_raw: str,
    degree: str,
    experience: str,
) -> dict:
    parsed = salary_norm.parse_salary(salary_raw)
    return {
        "company_norm": normalize_company(company_raw),
        "title_stem": normalize_title(title_raw),
        "city_norm": normalize_city(city),
        "degree": normalize_degree(degree),
        "experience": normalize_experience(experience),
        "salary_status": parsed["status"],
        "salary_low": parsed["salary_low"],
        "salary_high": parsed["salary_high"],
        "months": parsed["months"],
        "monthly_low": parsed["monthly_low"],
        "monthly_high": parsed["monthly_high"],
        "monthly_median": parsed["monthly_median"],
        "salary_basis": parsed["norm_basis"],
        "salary_confidence": parsed["confidence"],
        "salary_reason": parsed["reason"],
    }


def label_degree(value: str) -> str:
    return DEGREE_LABELS.get(value, value)


def label_experience(value: str) -> str:
    return EXPERIENCE_LABELS.get(value, value)

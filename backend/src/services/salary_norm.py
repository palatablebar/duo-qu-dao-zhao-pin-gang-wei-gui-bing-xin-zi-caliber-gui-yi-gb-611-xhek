"""算法 A｜薪资口径归一（纯函数、确定性、不访问网络）。

口径定义（README §10 与页面「薪资口径」列一致）：

1. 先做字符归一：NFKC 全角→半角、`～ ~ — – 至` → `-`、去首尾空白；
2. `N薪` 提取发薪月数 months（缺省 12，合法区间 12–24）；
3. `面议 / 面谈 / 详谈 / 待定 / 保密` → 不可比档：monthly_median = None，confidence = 0.2；
4. 金额单位：`k/千` = 1000，`万/w` = 10000；`x-yk` 这类只标在后一个数字上的单位会向左继承；
5. `年薪 / 年包` 模式：先得到年薪总额，再 ÷ 12 得月薪；
6. 月薪口径：`salary_low/high` 为名义月薪，`monthly_low/high = 名义区间 × 12 ÷ months`，
   `monthly_median = 区间中位 × 12 ÷ months`；
7. 非法（解析不出金额、量级超界）与矛盾（low > high）→ status=unparsed，进 unparsed 列表并计入失败率。
"""
from __future__ import annotations

import re
import unicodedata

from src.constants.enums import ParseStatus

NEGOTIABLE_PATTERN = re.compile(r"面议|面谈|详谈|待定|保密|另议")
MONTHS_PATTERN = re.compile(r"(\d{1,2})\s*薪")
AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(万|w|千|k)?")

UNIT_MULTIPLIER = {"万": 10000, "w": 10000, "千": 1000, "k": 1000, "": 1}

NOISE_TOKENS = (
    "年薪制", "年薪", "年包", "月薪", "税前", "税后", "基本工资", "综合薪资", "综合月薪",
    "薪资", "工资", "人民币", "元/月", "元每月", "元/月薪", "每月", "/月", "元", "起",
    "以上", "以下", "左右", "之间", "以内", "急聘", "诚聘", "高薪", "可谈",
)

DASH_CHARS = ("～", "~", "—", "–", "－", "至", "到")
MONTH_MIN, MONTH_MAX = 12, 24
MONTHLY_FLOOR, MONTHLY_CEIL = 500, 500000


def normalize_raw(raw: str | None) -> str:
    text = unicodedata.normalize("NFKC", raw or "").strip()
    for dash in DASH_CHARS:
        text = text.replace(dash, "-")
    text = text.replace("，", ",").replace("、", ",").replace("·", " ").replace("•", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _round(value: float) -> int:
    """确定性取整：四舍五入到整数元（Python round 对 .5 走偶数，仍逐次一致）。"""
    return int(round(value))


def _result(
    status: str,
    *,
    raw: str,
    basis: str,
    reason: str | None = None,
    months: int = 12,
    salary_low: int | None = None,
    salary_high: int | None = None,
    monthly_low: int | None = None,
    monthly_high: int | None = None,
    monthly_median: int | None = None,
    confidence: float = 0.0,
    annual_total: int | None = None,
) -> dict:
    return {
        "status": status,
        "reason": reason,
        "raw": raw,
        "months": months,
        "salary_low": salary_low,
        "salary_high": salary_high,
        "monthly_low": monthly_low,
        "monthly_high": monthly_high,
        "monthly_median": monthly_median,
        "annual_total": annual_total,
        "confidence": confidence,
        "norm_basis": basis,
    }


def parse_salary(raw: str | None) -> dict:
    original = (raw or "").strip()
    text = normalize_raw(original)
    if not text:
        return _result(
            ParseStatus.UNPARSED.value,
            raw=original,
            reason="薪资原值为空",
            basis=f"原值「{original}」：空值，无法归一",
        )
    if NEGOTIABLE_PATTERN.search(text):
        return _result(
            ParseStatus.NEGOTIABLE.value,
            raw=original,
            reason="面议无区间",
            basis=f"原值「{original}」：面议，无具体区间，按月薪不可比档位入库（confidence 0.2）",
            confidence=0.2,
        )

    work = text
    months = 12
    months_match = MONTHS_PATTERN.search(work)
    if months_match:
        months = max(MONTH_MIN, min(MONTH_MAX, int(months_match.group(1))))
        work = f"{work[: months_match.start()]} {work[months_match.end():]}"

    annual_mode = any(token in work for token in ("年薪", "年包"))
    for token in NOISE_TOKENS:
        work = work.replace(token, " ")
    work = re.sub(r"[\s,;:()\[\]{}]+", " ", work)

    matches = [(item.group(1), item.group(2)) for item in AMOUNT_PATTERN.finditer(work)]
    if not matches:
        return _result(
            ParseStatus.UNPARSED.value,
            raw=original,
            reason="未识别到金额",
            basis=f"原值「{original}」：未识别到金额，进入不可比清单",
        )

    shared_unit = next((unit for _, unit in matches if unit), "")
    inherited = any(not unit for _, unit in matches) and bool(shared_unit)

    amounts: list[float] = []
    for value_text, unit in matches[:2]:
        multiplier = UNIT_MULTIPLIER[unit or shared_unit]
        amounts.append(float(value_text) * multiplier)

    if len(amounts) == 1:
        low = high = amounts[0]
        single = True
    else:
        low, high = amounts[0], amounts[1]
        single = False

    if low > high:
        return _result(
            ParseStatus.UNPARSED.value,
            raw=original,
            reason="区间矛盾：下限高于上限",
            basis=f"原值「{original}」：区间下限 {low:g} 高于上限 {high:g}，判为矛盾数据",
        )

    basis_months = 12 if annual_mode else months
    annual_total = None
    if annual_mode:
        annual_total = _round((low + high) / 2)
        low = low / 12
        high = high / 12

    if low < MONTHLY_FLOOR or high > MONTHLY_CEIL:
        return _result(
            ParseStatus.UNPARSED.value,
            raw=original,
            reason="量级超出月薪可比范围",
            basis=f"原值「{original}」：折月后区间 {low:g}-{high:g} 超出可比范围 {MONTHLY_FLOOR}-{MONTHLY_CEIL}",
        )

    salary_low = _round(low)
    salary_high = _round(high)
    monthly_low = _round(low * 12 / basis_months)
    monthly_high = _round(high * 12 / basis_months)
    monthly_median = _round(((low + high) / 2) * 12 / basis_months)

    confidence = 0.95
    if single:
        confidence -= 0.12
    if inherited:
        confidence -= 0.05
    if basis_months != 12:
        confidence -= 0.03
    if annual_mode:
        confidence -= 0.08
    confidence = round(max(0.3, confidence), 2)

    if annual_mode:
        basis = (
            f"原值「{original}」：年薪总额 {annual_total} 元 ÷ 12 = 月薪 "
            f"{salary_low}-{salary_high}，中位 {monthly_median}"
        )
    else:
        basis = (
            f"原值「{original}」：名义月薪 {salary_low}-{salary_high} × 12 ÷ {basis_months} 薪 = "
            f"月薪 {monthly_low}-{monthly_high}，中位 {monthly_median}"
        )

    return _result(
        ParseStatus.PARSED.value,
        raw=original,
        basis=basis,
        months=basis_months,
        salary_low=salary_low,
        salary_high=salary_high,
        monthly_low=monthly_low,
        monthly_high=monthly_high,
        monthly_median=monthly_median,
        confidence=confidence,
        annual_total=annual_total,
    )


def parse_many(raws: list[str]) -> dict:
    """批量归一：保留输入顺序，输出 unparsed 清单与失败率。"""
    items = [parse_salary(raw) for raw in raws]
    unparsed = [
        {"index": index, "raw": item["raw"], "reason": item["reason"]}
        for index, item in enumerate(items)
        if item["status"] == ParseStatus.UNPARSED.value
    ]
    total = len(items)
    parsed = sum(1 for item in items if item["status"] == ParseStatus.PARSED.value)
    negotiable = sum(1 for item in items if item["status"] == ParseStatus.NEGOTIABLE.value)
    stats = {
        "total": total,
        "parsed": parsed,
        "negotiable": negotiable,
        "unparsed": len(unparsed),
        "fail_rate": round(len(unparsed) / total, 4) if total else 0.0,
        "noncomparable_rate": round((len(unparsed) + negotiable) / total, 4) if total else 0.0,
    }
    return {"items": items, "unparsed": unparsed, "stats": stats}

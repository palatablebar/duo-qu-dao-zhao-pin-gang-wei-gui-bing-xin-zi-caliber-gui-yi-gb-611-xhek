"""客户视图的脱敏工具（viewer 与对外导出共用）。"""
from __future__ import annotations


def mask_company(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return "某单位"
    head = cleaned[0]
    return f"{head}****（脱敏）"


def mask_text(text: str, company_raw: str) -> str:
    if not text or not company_raw:
        return text
    return text.replace(company_raw, mask_company(company_raw))

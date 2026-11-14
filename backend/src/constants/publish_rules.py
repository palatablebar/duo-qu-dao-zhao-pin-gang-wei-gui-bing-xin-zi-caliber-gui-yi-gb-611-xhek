"""发布口径规则（复核结论 -> 可发布岗位的唯一判定处）。

客户视图与发布清单只认这里的规则：

1. 只有「审核通过」的簇可以发布：`merge`（确认合并）与 `keep`（保持原样）视为通过；
2. `split`（拆分）不发布原合并行，而是把簇内每条原始岗位作为独立岗位发布；
3. 需要人工复核但还没有结论的簇（`needs_review=True` 且无有效结论）不发布，只计入待复核；
4. 已过期的岗位不发布，计入已撤回；
5. 当规则版本或归并阈值变化时，`rule_signature` 变化，旧发布版本立即失效，
   新版本不沿用旧版本的人工结论，所有待复核簇重新排队。

规则常量一旦调整，必须提升 `REVIEW_RULE_VERSION`，让旧发布版本自动失效。
"""
from __future__ import annotations

from src.config.settings import settings

# 规则语义版本：修改本文件中的发布/复核判定逻辑时必须 +1。
REVIEW_RULE_VERSION = "review-rules-v1"

# 只有人工审核通过的结论才发布（merge / keep）。
PUBLISH_REQUIRES_APPROVAL = True

# 允许发布的结论集合。
APPROVED_DECISIONS = ("merge", "keep")


def rule_version() -> str:
    return settings.review_rule_version or REVIEW_RULE_VERSION


def rule_signature(threshold: float | None) -> str:
    """发布口径签名：规则版本 + 归并阈值 + 是否要求人工审核。

    任何一个组成部分变化，签名就变化，旧发布版本立即失效。
    """
    value = float(threshold if threshold is not None else 0.0)
    return (
        f"{rule_version()}|threshold={value:.2f}"
        f"|require_approval={int(PUBLISH_REQUIRES_APPROVAL)}"
    )


def review_signature() -> str:
    """复核结论的规则签名：只含规则版本与审核要求。

    规则版本变化后，旧结论不再自动视为「审核通过」，对应的簇重新进入待复核队列；
    结论本身保留为历史记录（不删除）。
    """
    return f"{rule_version()}|require_approval={int(PUBLISH_REQUIRES_APPROVAL)}"


def is_approved(decision: str | None) -> bool:
    if decision is None:
        return not PUBLISH_REQUIRES_APPROVAL
    return decision in APPROVED_DECISIONS

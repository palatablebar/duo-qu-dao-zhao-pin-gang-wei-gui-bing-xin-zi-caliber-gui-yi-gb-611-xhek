"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，各项目的展示名与职责不同。
"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "平台管理员",
    Role.ANALYST.value: "岗位运营专员",
    Role.VIEWER.value: "客户只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护渠道与归并阈值、发起归并、导出发布清单、查看审计",
    Role.ANALYST.value: "发起归并、复核归并簇（合并/拆分）、查看原始岗位明细",
    Role.VIEWER.value: "只读查看总览与归并结果，精确公司名脱敏，不能运行/复核/导出",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "channel:read", "channel:write",
        "post:read",
        "cluster:read", "cluster:review",
        "run:read", "run:create",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "channel:read",
        "post:read",
        "cluster:read", "cluster:review",
        "run:read", "run:create",
        "export:read", "overview:read",
    },
    Role.VIEWER.value: {
        "channel:read", "post:read", "cluster:read", "overview:read",
    },
}

CHANNEL_WRITE_ROLES = (Role.ADMIN.value,)
RUN_CREATE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())

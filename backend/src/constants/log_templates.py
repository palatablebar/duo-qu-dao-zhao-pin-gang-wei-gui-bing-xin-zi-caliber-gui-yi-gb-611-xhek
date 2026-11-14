"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "channel.create": "登记渠道",
    "channel.update": "修改渠道",
    "run.create": "发起归并",
    "run.complete": "归并完成",
    "review.create": "复核归并簇",
    "salary.normalize": "薪资口径试算",
    "export.clusters": "导出归并清单",
    "export.reviews": "导出复核记录",
    "http.mutation": "写请求",
}

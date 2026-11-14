"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "channel.create": "登记渠道",
    "channel.update": "修改渠道",
    "run.create": "发起归并",
    "run.complete": "归并完成",
    "review.create": "复核归并簇",
    "publication.build": "生成发布版本",
    "salary.normalize": "薪资口径试算",
    "export.clusters": "导出客户发布清单",
    "export.posts": "导出原始来稿口径",
    "export.reviews": "导出复核记录",
    "export.runs": "导出运行记录",
    "http.mutation": "写请求",
}

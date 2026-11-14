"""导出服务：客户发布清单 / 原始岗位口径对照 / 复核记录 / 运行记录。

口径约定：

- `clusters.csv` = 客户清单，和客户入口（viewer 的 `/api/clusters`）共用
  `publication_service.customer_rows()` 这一个定义：同一发布版本、同一排序、同一批字段，
  不含精确公司名与内部薪资依据；导出逐项数与客户列表一致；
- `posts.csv` 是内部原始来稿口径对照（admin / analyst 专用），完整保留原值与归一过程；
- `reviews.csv` 导出全部复核记录，重算后原簇已替换的记录用快照字段展示，不丢行。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    DEGREE_LABELS,
    EXPERIENCE_LABELS,
    PARSE_STATUS_LABELS,
    REVIEW_DECISION_LABELS,
    TRIGGER_LABELS,
)
from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.models.run import Run
from src.services import publication_service
from src.utils.csv_export import to_csv
from src.utils.masking import mask_company


def _stamp(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return value.strftime(fmt) if value else ""


def current_version(db: Session) -> dict:
    """导出时统一取当前发布版本，内部材料与客户清单按同一版本号留痕。"""
    publication = publication_service.ensure_current(db, actor="system")
    return publication_service.serialize_header(
        publication, db.get(Run, publication.run_id) if publication.run_id else None
    )


def clusters_csv(db: Session, run_id: int | None = None) -> bytes:
    """客户发布清单：当前 active 版本里的 published 岗位，与客户列表逐项一致。

    `run_id` 仅用于审计标注：客户清单永远取当前发布版本，不会因为传了历史运行
    就泄漏未复核 / 已撤回口径。
    """
    publication, items = publication_service.customer_rows(db)
    headers = [
        "发布版本", "口径版本", "归并运行", "岗位序号", "岗位ID", "来源", "公司", "职位", "城市",
        "薪资口径状态", "月薪下限", "月薪上限", "月薪中位", "发薪月数", "渠道数", "渠道",
        "成员数", "消重条数", "置信度", "学历", "经验", "最近发布", "过期时间",
    ]
    rows = [
        [
            publication.version_no,
            # 只给规则版本，不下发阈值等内部口径参数。
            publication.rule_version,
            publication.run_id or "",
            item.ordinal,
            item.public_id,
            "拆分岗位" if item.source_kind == "post" else "归并簇",
            mask_company(item.company_display),
            item.title_display,
            item.city,
            PARSE_STATUS_LABELS.get(item.salary_status, item.salary_status),
            item.salary_low if item.salary_low is not None else "",
            item.salary_high if item.salary_high is not None else "",
            item.monthly_median if item.monthly_median is not None else "不可比",
            item.months,
            item.channel_count,
            "、".join(item.channels or []),
            item.member_count,
            item.dup_removed,
            f"{item.confidence:.3f}",
            DEGREE_LABELS.get(item.degree, item.degree),
            EXPERIENCE_LABELS.get(item.experience, item.experience),
            _stamp(item.published_at, "%Y-%m-%d"),
            _stamp(item.expire_at, "%Y-%m-%d"),
        ]
        for item in items
    ]
    return to_csv(headers, rows)


def posts_csv(db: Session) -> bytes:
    rows = db.execute(select(Post, Channel).join(Channel, Post.channel_id == Channel.id).order_by(Post.id)).all()
    headers = [
        "岗位ID", "渠道编码", "渠道名称", "外部ID", "公司", "公司归一", "职位", "职位词干", "城市",
        "薪资原值", "口径状态", "名义月薪下限", "名义月薪上限", "发薪月数",
        "归一后月薪下限", "归一后月薪上限", "月薪中位", "口径说明", "置信度", "学历", "经验", "发布时间", "过期时间",
    ]
    body = [
        [
            post.id,
            channel.code,
            channel.name,
            post.external_id,
            post.company_raw,
            post.company_norm,
            post.title_raw,
            post.title_stem,
            post.city,
            post.salary_raw,
            PARSE_STATUS_LABELS.get(post.salary_status, post.salary_status),
            post.salary_low if post.salary_low is not None else "",
            post.salary_high if post.salary_high is not None else "",
            post.months,
            post.monthly_low if post.monthly_low is not None else "",
            post.monthly_high if post.monthly_high is not None else "",
            post.monthly_median if post.monthly_median is not None else "不可比",
            post.salary_basis,
            f"{post.salary_confidence:.2f}",
            DEGREE_LABELS.get(post.degree, post.degree),
            EXPERIENCE_LABELS.get(post.experience, post.experience),
            _stamp(post.published_at, "%Y-%m-%d"),
            _stamp(post.expire_at, "%Y-%m-%d"),
        ]
        for post, channel in rows
    ]
    return to_csv(headers, body)


def reviews_csv(db: Session) -> bytes:
    reviews = db.scalars(select(Review).order_by(Review.id)).all()
    clusters = {item.id: item for item in db.scalars(select(Cluster)).all()}
    runs = {item.id: item for item in db.scalars(select(Run)).all()}
    headers = [
        "复核ID", "簇ID", "簇指纹", "运行编号", "公司", "职位", "城市", "成员数", "结论",
        "复核人", "备注", "复核时间",
    ]
    body = []
    for review in reviews:
        cluster = clusters.get(review.cluster_id) if review.cluster_id else None
        run = runs.get(review.run_id or 0)
        body.append(
            [
                review.id,
                review.cluster_id if review.cluster_id else "",
                review.fingerprint or (cluster.fingerprint if cluster else ""),
                run.run_no if run else "",
                cluster.company_display if cluster else review.company_display,
                cluster.title_display if cluster else review.title_display,
                cluster.city if cluster else "",
                cluster.member_count if cluster else "",
                REVIEW_DECISION_LABELS.get(review.decision, review.decision),
                review.reviewer,
                review.note or "",
                _stamp(review.updated_at),
            ]
        )
    return to_csv(headers, body)


def runs_csv(db: Session) -> bytes:
    runs = db.scalars(select(Run).order_by(Run.id)).all()
    headers = [
        "运行编号", "触发方式", "状态", "阈值", "原始岗位", "归并簇", "消重条数",
        "不可比占比", "操作人", "开始时间", "结束时间",
    ]
    body = [
        [
            run.run_no,
            TRIGGER_LABELS.get(run.trigger, run.trigger),
            run.status,
            f"{run.threshold:.2f}",
            run.posts_in,
            run.clusters_out,
            run.dupes_removed,
            f"{(run.metrics or {}).get('noncomparable_rate', 0) * 100:.2f}%",
            run.operator_email,
            _stamp(run.started_at),
            _stamp(run.finished_at),
        ]
        for run in runs
    ]
    return to_csv(headers, body)

"""导出服务：归并清单（含算法 A/B 结果） / 原始岗位口径对照 / 复核记录。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CLUSTER_STATUS_LABELS,
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
from src.services import run_service
from src.utils.csv_export import to_csv


def _stamp(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return value.strftime(fmt) if value else ""


def clusters_csv(db: Session, run_id: int | None = None) -> bytes:
    target = run_id or (run_service.latest_run(db).id if run_service.latest_run(db) else None)
    stmt = select(Cluster).where(Cluster.run_id == target) if target else select(Cluster).where(False)
    clusters = db.scalars(stmt.order_by(Cluster.id)).all()
    run = db.get(Run, target) if target else None
    headers = [
        "簇ID", "运行编号", "指纹", "公司", "职位", "城市", "月薪下限", "月薪上限",
        "月薪中位", "薪资口径", "渠道数", "渠道", "成员数", "消重条数", "置信度",
        "状态", "待复核", "学历", "经验", "最近发布", "过期时间", "归并阈值",
    ]
    rows = [
        [
            item.id,
            run.run_no if run else "",
            item.fingerprint,
            item.company_display,
            item.title_display,
            item.city,
            item.salary_low if item.salary_low is not None else "",
            item.salary_high if item.salary_high is not None else "",
            item.monthly_median if item.monthly_median is not None else "不可比",
            item.salary_basis,
            item.channel_count,
            "、".join(item.channels or []),
            item.member_count,
            item.dup_removed,
            f"{item.confidence:.3f}",
            CLUSTER_STATUS_LABELS.get(item.status, item.status),
            "是" if item.needs_review else "否",
            DEGREE_LABELS.get(item.degree, item.degree),
            EXPERIENCE_LABELS.get(item.experience, item.experience),
            _stamp(item.published_at, "%Y-%m-%d"),
            _stamp(item.expire_at, "%Y-%m-%d"),
            f"{run.threshold:.2f}" if run else "",
        ]
        for item in clusters
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
    headers = ["复核ID", "簇ID", "运行编号", "公司", "职位", "城市", "成员数", "结论", "复核人", "备注", "复核时间"]
    body = []
    for review in reviews:
        cluster = clusters.get(review.cluster_id)
        run = runs.get(review.run_id or 0)
        body.append(
            [
                review.id,
                review.cluster_id,
                run.run_no if run else "",
                cluster.company_display if cluster else "",
                cluster.title_display if cluster else "",
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

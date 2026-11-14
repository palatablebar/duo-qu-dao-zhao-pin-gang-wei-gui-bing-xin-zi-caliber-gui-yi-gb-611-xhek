"""总览：渠道 / 原始岗位 / 归并簇 / 待复核 / 薪资不可比占比 / worker 心跳。"""
from __future__ import annotations

import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    CLUSTER_STATUS_LABELS,
    PARSE_STATUS_LABELS,
    PARSE_STATUS_ORDER,
    Role,
)
from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.models.run import Run
from src.services import review_service, run_service
from src.services.post_service import mask_company
from src.utils.timeutil import iso_utc, local_now, utcnow


def worker_alive() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def _trend(db: Session) -> list[dict]:
    since = utcnow() - timedelta(days=8)
    runs = db.scalars(select(Run).where(Run.started_at >= since)).all()
    today = local_now().date()
    points = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = sum(
            1
            for run in runs
            if run.started_at
            and (run.started_at + timedelta(minutes=settings.app_timezone_offset_minutes)).date() == day
        )
        points.append({"date": day.isoformat(), "runs": count})
    return points


def overview(db: Session, role: str) -> dict:
    channels_total = db.scalar(select(func.count()).select_from(Channel)) or 0
    channels_enabled = db.scalar(select(func.count()).select_from(Channel).where(Channel.enabled.is_(True))) or 0
    posts_total = db.scalar(select(func.count()).select_from(Post)) or 0
    posts_expired = db.scalar(
        select(func.count()).select_from(Post).where(Post.expire_at.isnot(None), Post.expire_at < utcnow())
    ) or 0

    salary_rows = db.execute(select(Post.salary_status, func.count()).group_by(Post.salary_status)).all()
    salary_counts = {key: int(count) for key, count in salary_rows}
    negotiable = salary_counts.get("negotiable", 0)
    unparsed = salary_counts.get("unparsed", 0)

    latest = run_service.latest_run(db)
    counts = run_service.cluster_counts(db, latest.id if latest else None)
    reviews_total = db.scalar(select(func.count()).select_from(Review)) or 0

    channel_rows = db.execute(
        select(Channel.code, Channel.name, func.count(Post.id))
        .outerjoin(Post, Post.channel_id == Channel.id)
        .group_by(Channel.id)
        .order_by(Channel.id)
    ).all()

    status_rows = (
        db.execute(
            select(Cluster.status, func.count())
            .where(Cluster.run_id == latest.id, Cluster.run_id.isnot(None))
            .group_by(Cluster.status)
        ).all()
        if latest
        else []
    )

    top_clusters = []
    if latest:
        viewer = role == Role.VIEWER.value
        rows = db.scalars(
            select(Cluster)
            .where(Cluster.run_id == latest.id)
            .order_by(Cluster.member_count.desc(), Cluster.id)
            .limit(5)
        ).all()
        top_clusters = [
            {
                "id": row.id,
                "company": mask_company(row.company_display) if viewer else row.company_display,
                "title": row.title_display,
                "city": row.city,
                "member_count": row.member_count,
                "channel_count": row.channel_count,
                "monthly_median": row.monthly_median,
                "confidence": round(row.confidence, 3),
                "status_label": CLUSTER_STATUS_LABELS.get(row.status, row.status),
            }
            for row in rows
        ]

    return {
        "channels_total": channels_total,
        "channels_enabled": channels_enabled,
        "posts_total": posts_total,
        "posts_expired": posts_expired,
        "clusters_total": counts["clusters"],
        "clusters_multi": counts["multi"],
        "clusters_active": counts["active"],
        "clusters_expired": counts["expired"],
        "dupes_removed": latest.dupes_removed if latest else 0,
        "needs_review_total": counts["needs_review"],
        "reviews_total": reviews_total,
        "pending_total": review_service.pending_total(db, latest.id if latest else None),
        "salary": {
            "parsed": salary_counts.get("parsed", 0),
            "negotiable": negotiable,
            "unparsed": unparsed,
            "noncomparable_rate": round((negotiable + unparsed) / posts_total, 4) if posts_total else 0.0,
            "fail_rate": round(unparsed / posts_total, 4) if posts_total else 0.0,
        },
        "worker_alive": worker_alive(),
        "latest_run": {
            "id": latest.id,
            "run_no": latest.run_no,
            "status": latest.status,
            "threshold": round(latest.threshold or 0.0, 3),
            "posts_in": latest.posts_in,
            "clusters_out": latest.clusters_out,
            "dupes_removed": latest.dupes_removed,
            "started_at": iso_utc(latest.started_at),
            "finished_at": iso_utc(latest.finished_at),
            "metrics": latest.metrics or {},
        }
        if latest
        else None,
        "channel_mix": [
            {"code": code, "name": name, "count": int(count)} for code, name, count in channel_rows
        ],
        "salary_mix": [
            {
                "key": key,
                "label": PARSE_STATUS_LABELS.get(key, key),
                "count": salary_counts.get(key, 0),
            }
            for key in PARSE_STATUS_ORDER
        ],
        "status_mix": [
            {"key": key, "label": CLUSTER_STATUS_LABELS.get(key, key), "count": int(count)}
            for key, count in status_rows
        ],
        "top_clusters": top_clusters,
        "trend": _trend(db),
    }

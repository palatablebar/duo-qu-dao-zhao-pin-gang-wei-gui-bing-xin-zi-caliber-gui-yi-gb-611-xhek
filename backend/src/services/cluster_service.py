"""归并簇服务：列表、详情（成员对照 + 两两相似度）、viewer 脱敏。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CLUSTER_STATUS_LABELS,
    DEGREE_LABELS,
    EXPERIENCE_LABELS,
    PARSE_STATUS_LABELS,
    Role,
)
from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.services import dedupe
from src.services.post_service import mask_company, mask_text
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc


def serialize(cluster: Cluster, role: str, review: Review | None = None) -> dict:
    viewer = role == Role.VIEWER.value
    company = mask_company(cluster.company_display) if viewer else cluster.company_display
    return {
        "id": cluster.id,
        "run_id": cluster.run_id,
        "fingerprint": cluster.fingerprint,
        "blocking_key": cluster.blocking_key,
        "company_display": company,
        "company_norm": cluster.company_norm,
        "title_display": cluster.title_display,
        "title_stem": cluster.title_stem,
        "city": cluster.city,
        "salary_low": cluster.salary_low,
        "salary_high": cluster.salary_high,
        "monthly_median": cluster.monthly_median,
        "salary_basis": cluster.salary_basis,
        "channels": cluster.channels or [],
        "channel_count": cluster.channel_count,
        "member_count": cluster.member_count,
        "dup_removed": cluster.dup_removed,
        "degree": cluster.degree,
        "degree_label": DEGREE_LABELS.get(cluster.degree, cluster.degree),
        "experience": cluster.experience,
        "experience_label": EXPERIENCE_LABELS.get(cluster.experience, cluster.experience),
        "published_at": iso_utc(cluster.published_at),
        "expire_at": iso_utc(cluster.expire_at),
        "status": cluster.status,
        "status_label": CLUSTER_STATUS_LABELS.get(cluster.status, cluster.status),
        "confidence": round(cluster.confidence, 3),
        "needs_review": cluster.needs_review,
        "review_reason": cluster.review_reason or "",
        "golden_post_id": cluster.golden_post_id,
        "member_ids": cluster.member_ids or [],
        "review": {
            "decision": review.decision,
            "reviewer": review.reviewer,
            "note": review.note,
            "updated_at": iso_utc(review.updated_at),
        }
        if review
        else None,
        "created_at": iso_utc(cluster.created_at),
    }


def latest_run_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Cluster.run_id)))


def list_clusters(
    db: Session,
    *,
    role: str,
    run_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    multi_only: bool = False,
    needs_review: bool | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    target_run = run_id or latest_run_id(db)
    stmt = select(Cluster)
    count_stmt = select(func.count()).select_from(Cluster)
    if target_run:
        stmt = stmt.where(Cluster.run_id == target_run)
        count_stmt = count_stmt.where(Cluster.run_id == target_run)
    if status:
        stmt = stmt.where(Cluster.status == status)
        count_stmt = count_stmt.where(Cluster.status == status)
    if multi_only:
        stmt = stmt.where(Cluster.member_count > 1)
        count_stmt = count_stmt.where(Cluster.member_count > 1)
    if needs_review is not None:
        stmt = stmt.where(Cluster.needs_review.is_(needs_review))
        count_stmt = count_stmt.where(Cluster.needs_review.is_(needs_review))
    if q:
        like = f"%{q.strip()}%"
        clause = (
            Cluster.company_display.ilike(like)
            | Cluster.title_display.ilike(like)
            | Cluster.fingerprint.ilike(like)
        )
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Cluster.member_count.desc(), Cluster.id).limit(limit).offset(offset)
    ).all()
    reviews = {review.cluster_id: review for review in db.scalars(select(Review)).all()}
    return {
        "items": [serialize(row, role, reviews.get(row.id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "run_id": target_run,
    }


def get_cluster(db: Session, cluster_id: int, role: str) -> dict:
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise AppError("NOT_FOUND", 404, {"entity": "cluster", "id": cluster_id})
    review = db.scalar(select(Review).where(Review.cluster_id == cluster.id))
    payload = serialize(cluster, role, review)
    payload["members"] = _members(db, cluster, role)
    return payload


def _members(db: Session, cluster: Cluster, role: str) -> list[dict]:
    ids = [int(item) for item in (cluster.member_ids or [])]
    if not ids:
        return []
    rows = db.scalars(select(Post).where(Post.id.in_(ids)).order_by(Post.id)).all()
    channels = {channel.id: channel for channel in db.scalars(select(Channel)).all()}
    viewer = role == Role.VIEWER.value
    prepared = []
    for row in rows:
        channel = channels.get(row.channel_id)
        prepared.append(
            {
                "id": row.id,
                "external_id": row.external_id,
                "channel_code": channel.code if channel else "",
                "channel_name": channel.name if channel else "",
                "company_raw": mask_company(row.company_raw) if viewer else row.company_raw,
                "title_raw": row.title_raw,
                "city": row.city,
                "salary_raw": row.salary_raw,
                "salary_status": row.salary_status,
                "salary_status_label": PARSE_STATUS_LABELS.get(row.salary_status, row.salary_status),
                "monthly_low": row.monthly_low,
                "monthly_high": row.monthly_high,
                "monthly_median": row.monthly_median,
                "months": row.months,
                "degree_label": DEGREE_LABELS.get(row.degree, row.degree),
                "experience_label": EXPERIENCE_LABELS.get(row.experience, row.experience),
                "published_at": iso_utc(row.published_at),
                "raw_text": mask_text(row.raw_text, row.company_raw) if viewer else row.raw_text,
                "is_golden": row.id == cluster.golden_post_id,
                "company_norm": row.company_norm,
                "title_stem": row.title_stem,
                "monthly_low_value": row.monthly_low,
                "monthly_high_value": row.monthly_high,
                "monthly_median_value": row.monthly_median,
                "degree": row.degree,
                "experience": row.experience,
            }
        )

    golden = next((item for item in prepared if item["is_golden"]), prepared[0])
    for item in prepared:
        scored = dedupe.similarity(item, golden)
        item["similarity"] = scored
        for key in ("monthly_low_value", "monthly_high_value", "monthly_median_value"):
            item.pop(key, None)
    return prepared

"""复核服务：待复核队列、写结论、结论回写簇状态。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import CLUSTER_STATUS_LABELS, REVIEW_DECISION_LABELS, ReviewDecision
from src.models.cluster import Cluster
from src.models.review import Review
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, utcnow


def serialize(review: Review, cluster: Cluster | None = None) -> dict:
    return {
        "id": review.id,
        "cluster_id": review.cluster_id,
        "run_id": review.run_id,
        "decision": review.decision,
        "decision_label": REVIEW_DECISION_LABELS.get(review.decision, review.decision),
        "reviewer": review.reviewer,
        "note": review.note,
        "created_at": iso_utc(review.created_at),
        "updated_at": iso_utc(review.updated_at),
        "cluster": {
            "id": cluster.id,
            "fingerprint": cluster.fingerprint,
            "company_display": cluster.company_display,
            "title_display": cluster.title_display,
            "city": cluster.city,
            "member_count": cluster.member_count,
            "monthly_median": cluster.monthly_median,
            "status": cluster.status,
            "status_label": CLUSTER_STATUS_LABELS.get(cluster.status, cluster.status),
        }
        if cluster
        else None,
    }


def list_reviews(db: Session, decision: str | None, limit: int, offset: int) -> dict:
    stmt = select(Review)
    count_stmt = select(func.count()).select_from(Review)
    if decision:
        stmt = stmt.where(Review.decision == decision)
        count_stmt = count_stmt.where(Review.decision == decision)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Review.id.desc()).limit(limit).offset(offset)).all()
    clusters = {item.id: item for item in db.scalars(select(Cluster)).all()}
    return {
        "items": [serialize(row, clusters.get(row.cluster_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _latest_run_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Cluster.run_id)))


def pending_clusters(db: Session, limit: int = 20, offset: int = 0, run_id: int | None = None) -> dict:
    """待复核队列只看「最近一次归并运行」的簇：重跑后旧簇不再重复排队。"""
    target_run = run_id if run_id is not None else _latest_run_id(db)
    reviewed = select(Review.cluster_id)
    conditions = [Cluster.needs_review.is_(True), Cluster.id.not_in(reviewed)]
    if target_run:
        conditions.append(Cluster.run_id == target_run)
    stmt = select(Cluster).where(*conditions)
    count_stmt = select(func.count()).select_from(Cluster).where(*conditions)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Cluster.member_count.desc(), Cluster.id).limit(limit).offset(offset)).all()
    return {"items": [_pending_row(row) for row in rows], "total": total, "limit": limit, "offset": offset, "run_id": target_run}


def _pending_row(cluster: Cluster) -> dict:
    return {
        "id": cluster.id,
        "fingerprint": cluster.fingerprint,
        "company_display": cluster.company_display,
        "title_display": cluster.title_display,
        "city": cluster.city,
        "member_count": cluster.member_count,
        "channel_count": cluster.channel_count,
        "salary_basis": cluster.salary_basis,
        "monthly_median": cluster.monthly_median,
        "confidence": round(cluster.confidence, 3),
        "status": cluster.status,
        "status_label": CLUSTER_STATUS_LABELS.get(cluster.status, cluster.status),
        "reason": cluster.review_reason or _reason(cluster),
    }


def _reason(cluster: Cluster) -> str:
    """兜底文案：老数据没有 review_reason 时按成员数说明。"""
    if cluster.member_count > 1:
        return f"{cluster.member_count} 条来自不同渠道，写法不一致"
    return "算法标记待人工确认"


def upsert_decision(
    db: Session,
    *,
    cluster_id: int,
    decision: str,
    note: str | None,
    reviewer: str,
    seed_key: str | None = None,
) -> Review:
    if decision not in {item.value for item in ReviewDecision}:
        raise AppError("VALIDATION", 422, {"field": "decision", "allowed": [item.value for item in ReviewDecision]})
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise not_found("cluster", cluster_id)
    review = db.scalar(select(Review).where(Review.cluster_id == cluster_id))
    if review is None:
        review = Review(
            cluster_id=cluster_id,
            run_id=cluster.run_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
            seed_key=seed_key,
        )
        db.add(review)
    elif seed_key:
        return review  # seed 不覆盖人工改过的结论
    else:
        review.decision = decision
        review.reviewer = reviewer
        review.note = note
        review.updated_at = utcnow()

    if decision == ReviewDecision.SPLIT.value:
        cluster.status = "merged"
    elif decision == ReviewDecision.MERGE.value and cluster.status != "expired":
        cluster.status = "active"
    cluster.updated_at = utcnow()
    db.flush()
    return review


def pending_total(db: Session, run_id: int | None = None) -> int:
    target_run = run_id if run_id is not None else _latest_run_id(db)
    reviewed = select(Review.cluster_id)
    conditions = [Cluster.needs_review.is_(True), Cluster.id.not_in(reviewed)]
    if target_run:
        conditions.append(Cluster.run_id == target_run)
    return db.scalar(select(func.count()).select_from(Cluster).where(*conditions)) or 0

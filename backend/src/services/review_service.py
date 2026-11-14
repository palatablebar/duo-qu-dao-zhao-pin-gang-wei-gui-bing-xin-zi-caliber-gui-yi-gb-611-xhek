"""复核服务：待复核队列、写结论、结论回写簇状态。

复核结论是「可发布口径」的来源：`merge` / `keep` 代表审核通过，`split` 代表拆成独立岗位。
写结论后立即触发一次发布版本重建，让客户入口与导出同步切到新口径。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import CLUSTER_STATUS_LABELS, REVIEW_DECISION_LABELS, ReviewDecision
from src.constants.publish_rules import review_signature
from src.models.cluster import Cluster
from src.models.review import Review
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, utcnow

# split 之后原簇不再作为合并岗位发布，但仍保留在库内可追溯。
SPLIT_CLUSTER_STATUS = "merged"


def serialize(review: Review, cluster: Cluster | None = None) -> dict:
    cluster_payload = None
    if cluster is not None:
        cluster_payload = {
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
    elif review.cluster_id is None:
        # 重算后原簇已被替换：仍用复核时留存的快照展示，复核记录不丢。
        cluster_payload = {
            "id": None,
            "fingerprint": review.fingerprint,
            "company_display": review.company_display,
            "title_display": review.title_display,
            "city": "",
            "member_count": None,
            "monthly_median": None,
            "status": "archived",
            "status_label": "历史簇已重算",
        }
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
        "cluster": cluster_payload,
    }


def list_reviews(db: Session, decision: str | None, limit: int, offset: int) -> dict:
    stmt = select(Review)
    count_stmt = select(func.count()).select_from(Review)
    if decision:
        stmt = stmt.where(Review.decision == decision)
        count_stmt = count_stmt.where(Review.decision == decision)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Review.id.desc()).limit(limit).offset(offset)).all()
    cluster_ids = [row.cluster_id for row in rows if row.cluster_id]
    clusters = (
        {item.id: item for item in db.scalars(select(Cluster).where(Cluster.id.in_(cluster_ids))).all()}
        if cluster_ids
        else {}
    )
    return {
        "items": [serialize(row, clusters.get(row.cluster_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _latest_run_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Cluster.run_id)))


def _pending_conditions(db: Session, run_id: int | None) -> list:
    target_run = run_id if run_id is not None else _latest_run_id(db)
    # 只有「当前规则签名下」的结论才算已复核；规则变化后旧结论保留为历史，
    # 对应簇重新排队复核，直到有人按新规则重新给出结论。
    current = review_signature()
    reviewed = select(Review.cluster_id).where(
        Review.cluster_id.isnot(None), Review.rule_signature == current
    )
    conditions = [Cluster.needs_review.is_(True), Cluster.id.not_in(reviewed)]
    if target_run:
        conditions.append(Cluster.run_id == target_run)
    return conditions


def pending_clusters(db: Session, limit: int = 20, offset: int = 0, run_id: int | None = None) -> dict:
    """待复核队列只看「最近一次归并运行」中没有结论的簇：重跑后旧簇不再重复排队。"""
    conditions = _pending_conditions(db, run_id)
    stmt = select(Cluster).where(*conditions)
    count_stmt = select(func.count()).select_from(Cluster).where(*conditions)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Cluster.member_count.desc(), Cluster.id).limit(limit).offset(offset)
    ).all()
    target_run = run_id if run_id is not None else _latest_run_id(db)
    return {
        "items": [_pending_row(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "run_id": target_run,
    }


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


def _apply_cluster_state(cluster: Cluster, decision: str) -> None:
    if decision == ReviewDecision.SPLIT.value:
        cluster.status = SPLIT_CLUSTER_STATUS
    elif cluster.status != "expired":
        cluster.status = "active"


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
        raise AppError(
            "VALIDATION", 422, {"field": "decision", "allowed": [item.value for item in ReviewDecision]}
        )
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise not_found("cluster", cluster_id)
    review = db.scalar(select(Review).where(Review.cluster_id == cluster_id))
    if review is None and seed_key:
        review = db.scalar(select(Review).where(Review.seed_key == seed_key))
        if review is not None:
            # seed 重跑：已有结论（人工改过的也不覆盖），只把结论挂回当前簇。
            if review.cluster_id != cluster_id:
                review.cluster_id = cluster_id
                review.run_id = cluster.run_id
            _apply_cluster_state(cluster, review.decision)
            cluster.updated_at = utcnow()
            db.flush()
            return review
    if review is None:
        review = Review(
            cluster_id=cluster_id,
            run_id=cluster.run_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
            seed_key=seed_key,
            rule_signature=review_signature(),
        )
        db.add(review)
    elif seed_key:
        return review  # seed 不覆盖人工改过的结论
    else:
        review.decision = decision
        review.reviewer = reviewer
        review.note = note
        review.rule_signature = review_signature()
        review.updated_at = utcnow()

    review.fingerprint = cluster.fingerprint
    review.company_display = cluster.company_display
    review.title_display = cluster.title_display
    review.rule_signature = review_signature()
    _apply_cluster_state(cluster, review.decision)
    cluster.updated_at = utcnow()
    db.flush()
    return review


def pending_total(db: Session, run_id: int | None = None) -> int:
    conditions = _pending_conditions(db, run_id)
    return db.scalar(select(func.count()).select_from(Cluster).where(*conditions)) or 0


def review_counts(db: Session, run_id: int | None = None) -> dict:
    """复核版面口径：待复核 / 可发布 / 已撤回 / 已拆分的簇数量。"""
    target_run = run_id if run_id is not None else _latest_run_id(db)
    cluster_ids = (
        select(Cluster.id).where(Cluster.run_id == target_run) if target_run else select(Cluster.id)
    )
    decisions: dict[str, int] = {}
    rows = db.execute(
        select(Review.decision, func.count())
        .where(Review.cluster_id.in_(cluster_ids))
        .group_by(Review.decision)
    ).all()
    for key, count in rows:
        decisions[key] = int(count)
    return {
        "run_id": target_run,
        "decisions": decisions,
        "pending": pending_total(db, target_run),
    }

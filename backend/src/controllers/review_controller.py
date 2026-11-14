"""复核控制器：写结论 + 领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, publication_service, review_service
from src.models.run import Run


def list_reviews(db: Session, **filters) -> dict:
    return review_service.list_reviews(db, **filters)


def pending(db: Session, limit: int, offset: int) -> dict:
    return review_service.pending_clusters(db, limit=limit, offset=offset)


def counts(db: Session) -> dict:
    payload = review_service.review_counts(db)
    publication = publication_service.ensure_current(db, actor="system")
    run = db.get(Run, publication.run_id) if publication.run_id else None
    payload["publication"] = publication_service.serialize_header(publication, run)
    return payload


def create_review(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    review = review_service.upsert_decision(
        db,
        cluster_id=int(payload["cluster_id"]),
        decision=payload["decision"],
        note=payload.get("note"),
        reviewer=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="review.create",
        entity="cluster",
        entity_id=review.cluster_id,
        detail={"decision": review.decision, "note": review.note},
        ip=request.client.host if request.client else None,
    )
    db.flush()
    # 复核结论立即固化到发布版本：客户入口与导出同一时刻切到新口径。
    publication = publication_service.ensure_current(db, actor=principal["email"], commit=False)
    db.commit()
    result = review_service.serialize(review)
    result["publication"] = publication_service.serialize_header(publication)
    return result

"""复核控制器：写结论 + 领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, review_service


def list_reviews(db: Session, **filters) -> dict:
    return review_service.list_reviews(db, **filters)


def pending(db: Session, limit: int, offset: int) -> dict:
    return review_service.pending_clusters(db, limit=limit, offset=offset)


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
    db.commit()
    return review_service.serialize(review)

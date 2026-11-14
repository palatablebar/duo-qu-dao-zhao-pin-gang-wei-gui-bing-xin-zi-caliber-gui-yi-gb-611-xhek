"""导出控制器：CSV 响应 + 审计。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers


def _audit(db: Session, principal: dict, action: str, entity: str, content: bytes, request: Request, entity_id=None) -> None:
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail={"bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()


def clusters_csv(db: Session, run_id: int | None, principal: dict, request: Request) -> Response:
    content = export_service.clusters_csv(db, run_id)
    _audit(db, principal, "export.clusters", "cluster", content, request, run_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("jobmerge-clusters.csv"),
    )


def posts_csv(db: Session, principal: dict, request: Request) -> Response:
    content = export_service.posts_csv(db)
    _audit(db, principal, "export.clusters", "post", content, request)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("jobmerge-posts.csv"),
    )


def reviews_csv(db: Session, principal: dict, request: Request) -> Response:
    content = export_service.reviews_csv(db)
    _audit(db, principal, "export.reviews", "review", content, request)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("jobmerge-reviews.csv"),
    )


def runs_csv(db: Session, principal: dict, request: Request) -> Response:
    content = export_service.runs_csv(db)
    _audit(db, principal, "export.clusters", "run", content, request)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("jobmerge-runs.csv"),
    )

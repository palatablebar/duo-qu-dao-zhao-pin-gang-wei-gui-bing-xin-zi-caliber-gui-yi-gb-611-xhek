from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import cluster_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.utils.pagination import page_params

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("")
def list_clusters(
    run_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    multi: bool = False,
    needs_review: bool | None = None,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return cluster_controller.list_clusters(
        db,
        role=principal["role"],
        run_id=run_id,
        status=status,
        q=q,
        multi_only=multi,
        needs_review=needs_review,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{cluster_id}")
def get_cluster(
    cluster_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return cluster_controller.get_cluster(db, cluster_id, principal["role"])

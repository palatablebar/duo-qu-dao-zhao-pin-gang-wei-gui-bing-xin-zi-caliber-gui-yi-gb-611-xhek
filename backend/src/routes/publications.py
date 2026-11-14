from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.middlewares.rbac import READ_ROLES, require_roles
from src.services import publication_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/publications", tags=["publications"])


@router.get("/current")
def current(
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    """当前发布版本的岗位行。

    viewer 只能拿到 published 行（拆分岗位已独立成行，脱敏）；
    admin / analyst 可带 status 过滤，核对「可发布 / 已撤回」。
    """
    page = page_params(limit, offset)
    return publication_service.list_current(
        db,
        viewer=principal["role"] == "viewer",
        status=status,
        q=q,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/history")
def history(
    limit: int = Query(20),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, 0)
    return publication_service.history(db, limit=page.limit)


@router.get("/{item_id}")
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return publication_service.get_item(db, item_id, viewer=principal["role"] == "viewer")

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import post_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.utils.pagination import page_params

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
def list_posts(
    channel_id: int | None = None,
    city: str | None = None,
    salary_status: str | None = None,
    q: str | None = None,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return post_controller.list_posts(
        db,
        role=principal["role"],
        channel_id=channel_id,
        city=city,
        salary_status=salary_status,
        q=q,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{post_id}")
def get_post(
    post_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return post_controller.get_post(db, post_id, principal["role"])

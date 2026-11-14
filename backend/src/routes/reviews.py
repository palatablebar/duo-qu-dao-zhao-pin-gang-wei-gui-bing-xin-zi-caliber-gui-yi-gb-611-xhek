from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import REVIEW_ROLES
from src.controllers import review_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.cluster import ReviewIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("")
def list_reviews(
    decision: str | None = None,
    limit: int = Query(30),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return review_controller.list_reviews(db, decision=decision, limit=page.limit, offset=page.offset)


@router.get("/pending")
def pending(
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return review_controller.pending(db, limit=page.limit, offset=page.offset)


@router.post("", status_code=201)
def create_review(
    payload: ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
) -> dict:
    return review_controller.create_review(db, payload.model_dump(), principal, request)

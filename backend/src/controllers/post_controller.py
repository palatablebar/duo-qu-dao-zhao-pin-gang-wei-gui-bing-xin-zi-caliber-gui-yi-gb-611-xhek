"""原始岗位控制器。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import post_service


def list_posts(db: Session, **filters) -> dict:
    return post_service.list_posts(db, **filters)


def get_post(db: Session, post_id: int, role: str) -> dict:
    return post_service.get_post(db, post_id, role)


def salary_breakdown(db: Session) -> dict:
    return post_service.salary_breakdown(db)

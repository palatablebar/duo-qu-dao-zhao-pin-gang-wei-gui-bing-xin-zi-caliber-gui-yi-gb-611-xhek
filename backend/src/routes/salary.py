from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import salary_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.salary import SalaryIn

router = APIRouter(prefix="/salary", tags=["salary"])


@router.get("/samples")
def samples(principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return salary_controller.samples()


@router.get("/breakdown")
def breakdown(db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return salary_controller.salary_breakdown(db)


@router.post("/normalize")
def normalize(
    payload: SalaryIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return salary_controller.normalize(payload.model_dump(), principal, request, db)

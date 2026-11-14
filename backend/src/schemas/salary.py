from __future__ import annotations

from pydantic import BaseModel, Field

from src.constants.limits import MAX_SALARY_RAW_LENGTH


class SalaryIn(BaseModel):
    raw: str = Field(min_length=1, max_length=MAX_SALARY_RAW_LENGTH)

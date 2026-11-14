from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.constants.limits import DEFAULT_SIMILARITY_THRESHOLD, MAX_SIMILARITY_THRESHOLD, MIN_SIMILARITY_THRESHOLD


class RunIn(BaseModel):
    trigger: Literal["manual", "schedule"] = "manual"
    threshold: float = Field(
        default=DEFAULT_SIMILARITY_THRESHOLD,
        ge=MIN_SIMILARITY_THRESHOLD,
        le=MAX_SIMILARITY_THRESHOLD,
    )

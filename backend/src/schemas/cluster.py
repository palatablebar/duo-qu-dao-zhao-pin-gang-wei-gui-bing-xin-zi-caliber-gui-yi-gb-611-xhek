from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewIn(BaseModel):
    cluster_id: int = Field(gt=0)
    decision: Literal["merge", "split", "keep"]
    note: str | None = Field(default=None, max_length=1000)

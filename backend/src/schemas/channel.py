from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CRON_PATTERN = r"^(\S+\s+){4}\S+$"


class ChannelIn(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["site", "api", "file", "manual"] = "site"
    crawl_cron: str = Field(default="0 6 * * *", pattern=CRON_PATTERN, max_length=40)
    endpoint: str | None = Field(default=None, max_length=255)
    owner: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=2000)
    enabled: bool = True


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: Literal["site", "api", "file", "manual"] | None = None
    crawl_cron: str | None = Field(default=None, pattern=CRON_PATTERN, max_length=40)
    endpoint: str | None = Field(default=None, max_length=255)
    owner: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None

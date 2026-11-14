"""归并簇：同一岗位在多渠道的重复挂载聚成一条，承载对外发布口径。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Cluster(Base):
    __tablename__ = "clusters"
    __table_args__ = (UniqueConstraint("run_id", "fingerprint", name="uq_clusters_run_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(32), index=True)
    blocking_key: Mapped[str] = mapped_column(String(220), default="")

    company_norm: Mapped[str] = mapped_column(String(120), index=True)
    company_display: Mapped[str] = mapped_column(String(160))
    title_stem: Mapped[str] = mapped_column(String(160), index=True)
    title_display: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(40), index=True)

    salary_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_median: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    salary_basis: Mapped[str] = mapped_column(Text, default="")

    member_ids: Mapped[list] = mapped_column(JSON, default=list)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    channel_count: Mapped[int] = mapped_column(Integer, default=1)
    member_count: Mapped[int] = mapped_column(Integer, default=1, index=True)
    dup_removed: Mapped[int] = mapped_column(Integer, default=0)

    degree: Mapped[str] = mapped_column(String(16), default="any")
    experience: Mapped[str] = mapped_column(String(16), default="any")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reason: Mapped[str] = mapped_column(String(200), default="")
    golden_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

"""发布口径：每次归并 / 复核结论 / 规则变化生成一个可发布的岗位版本。

`Publication` 是版本头，`PublicationItem` 是版本里的岗位行：

- 只有审核通过的簇可以发布：无需人工复核的簇视为算法通过，`merge`/`keep` 视为人工通过；
- 复核结论为 `split` 的簇不发布原合并行，改为把簇内原始岗位逐条作为独立岗位发布；
- 需要人工复核但还没有结论的簇不进入版本明细，只计入待复核；
- 已过期的岗位发布为 `withdrawn`，保留在版本内供页面核对，但不出现在客户清单；
- `rule_signature`（规则版本 + 阈值 + 审核要求）变化时，旧版本整体失效，
  新版本按新规则重建，客户入口与导出在同一时刻切到新版本。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    rule_version: Mapped[str] = mapped_column(String(64), default="")
    rule_signature: Mapped[str] = mapped_column(String(200), default="", index=True)
    state_hash: Mapped[str] = mapped_column(String(40), default="")
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(40), default="build")

    clusters_total: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    split_count: Mapped[int] = mapped_column(Integer, default=0)
    published_cluster_count: Mapped[int] = mapped_column(Integer, default=0)
    published_post_count: Mapped[int] = mapped_column(Integer, default=0)
    withdrawn_cluster_count: Mapped[int] = mapped_column(Integer, default=0)
    withdrawn_post_count: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    withdrawn_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[str] = mapped_column(String(160), default="system")
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublicationItem(Base):
    __tablename__ = "publication_items"
    __table_args__ = (
        UniqueConstraint("publication_id", "public_id", name="uq_publication_items_public"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), index=True
    )
    public_id: Mapped[str] = mapped_column(String(60), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0, index=True)
    source_kind: Mapped[str] = mapped_column(String(12), default="cluster")  # cluster | post

    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(12), nullable=True)

    status: Mapped[str] = mapped_column(String(12), default="published", index=True)
    withdraw_reason: Mapped[str] = mapped_column(String(40), default="")

    company_display: Mapped[str] = mapped_column(String(160), default="")
    company_norm: Mapped[str] = mapped_column(String(120), default="")
    title_display: Mapped[str] = mapped_column(String(200), default="")
    title_stem: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(40), default="")

    salary_status: Mapped[str] = mapped_column(String(16), default="parsed")
    salary_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_median: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_basis: Mapped[str] = mapped_column(Text, default="")
    months: Mapped[int] = mapped_column(Integer, default=12)

    degree: Mapped[str] = mapped_column(String(16), default="any")
    experience: Mapped[str] = mapped_column(String(16), default="any")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    channels: Mapped[list] = mapped_column(JSON, default=list)
    channel_count: Mapped[int] = mapped_column(Integer, default=1)
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    dup_removed: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

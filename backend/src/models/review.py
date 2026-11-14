"""复核：人工对一个归并簇给出合并 / 拆分 / 保持原样。一个簇保留一条有效结论。

`cluster_id` 允许为空且外键为 SET NULL：归并重跑清理历史簇时，复核结论仍然保留，
不会随簇级联删除（复核记录不能因重算丢失）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("cluster_id", name="uq_reviews_cluster"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(32), default="", index=True)
    company_display: Mapped[str] = mapped_column(String(160), default="")
    title_display: Mapped[str] = mapped_column(String(200), default="")
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(12), default="keep", index=True)
    reviewer: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 给出结论时的发布口径签名：规则/阈值一变，旧结论不再沿用（保留为历史记录）。
    rule_signature: Mapped[str] = mapped_column(String(200), default="", index=True)
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

"""原始岗位：某个渠道抓回来的一条招聘信息，附带薪资口径归一结果。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("channel_id", "external_id", name="uq_posts_channel_external"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(60), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)

    company_raw: Mapped[str] = mapped_column(String(160))
    company_norm: Mapped[str] = mapped_column(String(120), index=True)
    title_raw: Mapped[str] = mapped_column(String(200))
    title_stem: Mapped[str] = mapped_column(String(160), index=True)
    city: Mapped[str] = mapped_column(String(40), index=True)

    salary_raw: Mapped[str] = mapped_column(String(80))
    salary_status: Mapped[str] = mapped_column(String(16), default="unparsed", index=True)
    salary_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    months: Mapped[int] = mapped_column(Integer, default=12)
    monthly_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_median: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    salary_basis: Mapped[str] = mapped_column(Text, default="")
    salary_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    degree: Mapped[str] = mapped_column(String(16), default="any")
    experience: Mapped[str] = mapped_column(String(16), default="any")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")

    seed_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

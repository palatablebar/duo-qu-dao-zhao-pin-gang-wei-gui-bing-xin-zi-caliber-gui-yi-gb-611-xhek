"""渠道服务：登记 / 修改 / 列表（含抓取的岗位数）。"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_KIND_LABELS
from src.models.channel import Channel
from src.models.post import Post
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, utcnow


def serialize(channel: Channel, post_count: int = 0, expired_count: int = 0) -> dict:
    return {
        "id": channel.id,
        "code": channel.code,
        "name": channel.name,
        "kind": channel.kind,
        "kind_label": CHANNEL_KIND_LABELS.get(channel.kind, channel.kind),
        "crawl_cron": channel.crawl_cron,
        "endpoint": channel.endpoint,
        "owner": channel.owner,
        "note": channel.note,
        "enabled": channel.enabled,
        "post_count": post_count,
        "expired_count": expired_count,
        "last_crawled_at": iso_utc(channel.last_crawled_at),
        "created_at": iso_utc(channel.created_at),
    }


def _counts(db: Session) -> dict[int, tuple[int, int]]:
    """每个渠道：(已入库条数, 其中已过期条数)。"""
    expired_flag = case((Post.expire_at.isnot(None) & (Post.expire_at < utcnow()), 1), else_=0)
    rows = db.execute(
        select(Post.channel_id, func.count(), func.sum(expired_flag)).group_by(Post.channel_id)
    ).all()
    return {int(channel_id): (int(total), int(expired or 0)) for channel_id, total, expired in rows}


def list_channels(db: Session, q: str | None, kind: str | None, enabled: bool | None) -> dict:
    stmt = select(Channel)
    count_stmt = select(func.count()).select_from(Channel)
    if q:
        like = f"%{q.strip()}%"
        clause = Channel.name.ilike(like) | Channel.code.ilike(like)
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    if kind:
        stmt = stmt.where(Channel.kind == kind)
        count_stmt = count_stmt.where(Channel.kind == kind)
    if enabled is not None:
        stmt = stmt.where(Channel.enabled == enabled)
        count_stmt = count_stmt.where(Channel.enabled == enabled)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Channel.id)).all()
    counts = _counts(db)
    items = [serialize(row, *counts.get(row.id, (0, 0))) for row in rows]
    return {"items": items, "total": total, "limit": len(items), "offset": 0}


def get_channel(db: Session, channel_id: int) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise not_found("channel", channel_id)
    return channel


def create_channel(db: Session, payload: dict) -> Channel:
    exists = db.scalar(select(Channel).where(Channel.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"code": payload["code"]})
    channel = Channel(
        code=payload["code"],
        name=payload["name"],
        kind=payload.get("kind") or "site",
        crawl_cron=payload.get("crawl_cron") or "0 6 * * *",
        endpoint=payload.get("endpoint"),
        owner=payload.get("owner") or "云雀招聘聚合 · 岗位运营组",
        note=payload.get("note"),
        enabled=payload.get("enabled", True),
    )
    db.add(channel)
    db.flush()
    return channel


def update_channel(db: Session, channel: Channel, payload: dict) -> Channel:
    for field in ("name", "kind", "crawl_cron", "endpoint", "owner", "note", "enabled"):
        if field in payload and payload[field] is not None:
            setattr(channel, field, payload[field])
    db.flush()
    return channel

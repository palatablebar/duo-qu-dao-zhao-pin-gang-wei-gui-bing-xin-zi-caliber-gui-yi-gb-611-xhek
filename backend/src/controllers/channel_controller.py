"""渠道控制器：写操作记领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, channel_service


def list_channels(db: Session, **filters) -> dict:
    return channel_service.list_channels(db, **filters)


def get_channel(db: Session, channel_id: int) -> dict:
    channel = channel_service.get_channel(db, channel_id)
    return channel_service.serialize(channel)


def create_channel(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    channel = channel_service.create_channel(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="channel.create",
        entity="channel",
        entity_id=channel.id,
        detail={"code": channel.code, "name": channel.name, "crawl_cron": channel.crawl_cron},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return channel_service.serialize(channel)


def update_channel(db: Session, channel_id: int, payload: dict, principal: dict, request: Request) -> dict:
    channel = channel_service.get_channel(db, channel_id)
    channel_service.update_channel(db, channel, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="channel.update",
        entity="channel",
        entity_id=channel.id,
        detail={"fields": list(payload.keys()), "enabled": channel.enabled},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return channel_service.serialize(channel)

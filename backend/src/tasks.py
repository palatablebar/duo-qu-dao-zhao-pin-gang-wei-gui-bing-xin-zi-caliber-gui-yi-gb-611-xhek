"""Celery 任务：心跳、每日归并重算（对全部启用渠道重跑一次归并）。"""
from __future__ import annotations

import time

from sqlalchemy import select

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_refresh() -> dict:
    from src.config.database import session_scope
    from src.models.channel import Channel
    from src.services import audit_service, run_service

    with session_scope() as db:
        channels = db.scalars(select(Channel).where(Channel.enabled.is_(True))).all()
        run = run_service.create_and_execute(
            db,
            trigger="schedule",
            operator_email="scheduler@" + settings.app_name + ".io",
        )
        audit_service.record(
            db,
            actor_email="scheduler@" + settings.app_name + ".io",
            actor_role="admin",
            action="run.create",
            entity="run",
            entity_id=run.id,
            detail={"trigger": "schedule", "run_no": run.run_no, "channels": len(channels)},
            layer="worker",
        )
        result = {"channels": len(channels), "run_no": run.run_no, "clusters": run.clusters_out}
    logger.info("daily merge finished: %s", result)
    return result

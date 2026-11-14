"""运行服务：创建运行、执行归并、写库、列表。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.limits import DEFAULT_SIMILARITY_THRESHOLD
from src.models.cluster import Cluster
from src.models.run import Run
from src.services import merge_service
from src.utils.errors import AppError, bad_request
from src.utils.timeutil import iso_utc, local_now, utcnow


def serialize(run: Run) -> dict:
    return {
        "id": run.id,
        "run_no": run.run_no,
        "trigger": run.trigger,
        "status": run.status,
        "operator_email": run.operator_email,
        "threshold": round(run.threshold or 0.0, 3),
        "posts_in": run.posts_in,
        "clusters_out": run.clusters_out,
        "dupes_removed": run.dupes_removed,
        "metrics": run.metrics or {},
        "log_text": run.log_text,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }


def next_run_no(db: Session) -> str:
    prefix = f"M{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(Run).where(Run.run_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def execute_run(db: Session, run: Run) -> Run:
    run.status = "running"
    try:
        result = merge_service.execute_merge(db, run)
        metrics = result["metrics"]
        run.metrics = metrics
        run.log_text = result["log"]
        run.posts_in = int(metrics["posts_in"])
        run.clusters_out = int(metrics["clusters"])
        run.dupes_removed = int(metrics["dupes_removed"])
        run.status = result["status"]
    except Exception as exc:  # noqa: BLE001 - 运行失败要留痕，不抛 500
        run.status = "failed"
        run.log_text = f"归并失败：{exc}"
        run.metrics = {"error": str(exc)[:300]}
    run.finished_at = utcnow()
    db.flush()
    if run.status in {"success", "partial"}:
        # 归并结果落库后立刻重建发布版本：客户入口与导出随即切到新口径。
        from src.services import publication_service

        publication_service.ensure_current(
            db,
            actor=run.operator_email or "system",
            seed_key=f"seed-publication-{run.seed_key}" if run.seed_key else None,
            commit=False,
        )
    return run


def create_and_execute(
    db: Session,
    *,
    trigger: str,
    operator_email: str,
    threshold: float | None = None,
    seed_key: str | None = None,
) -> Run:
    if seed_key:
        existing = db.scalar(select(Run).where(Run.seed_key == seed_key))
        if existing is not None:
            return existing
    value = float(threshold if threshold is not None else DEFAULT_SIMILARITY_THRESHOLD)
    if not 0.5 <= value <= 0.99:
        raise bad_request("VALIDATION", {"field": "threshold", "min": 0.5, "max": 0.99})
    run = Run(
        run_no=next_run_no(db),
        trigger=trigger,
        status="running",
        operator_email=operator_email,
        threshold=round(value, 2),
        seed_key=seed_key,
    )
    db.add(run)
    db.flush()
    return execute_run(db, run)


def list_runs(db: Session, status: str | None, limit: int, offset: int) -> dict:
    stmt = select(Run)
    count_stmt = select(func.count()).select_from(Run)
    if status:
        stmt = stmt.where(Run.status == status)
        count_stmt = count_stmt.where(Run.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Run.id.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [serialize(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, {"entity": "run", "id": run_id})
    return run


def latest_run(db: Session) -> Run | None:
    return db.scalar(select(Run).order_by(Run.id.desc()).limit(1))


def cluster_counts(db: Session, run_id: int | None) -> dict:
    if run_id is None:
        return {"clusters": 0, "multi": 0, "needs_review": 0, "expired": 0, "active": 0}
    rows = db.execute(
        select(Cluster.status, func.count()).where(Cluster.run_id == run_id).group_by(Cluster.status)
    ).all()
    by_status = {key: int(count) for key, count in rows}
    multi = db.scalar(
        select(func.count()).select_from(Cluster).where(Cluster.run_id == run_id, Cluster.member_count > 1)
    ) or 0
    needs_review = db.scalar(
        select(func.count()).select_from(Cluster).where(Cluster.run_id == run_id, Cluster.needs_review.is_(True))
    ) or 0
    return {
        "clusters": sum(by_status.values()),
        "multi": int(multi),
        "needs_review": int(needs_review),
        "expired": by_status.get("expired", 0),
        "active": by_status.get("active", 0),
    }

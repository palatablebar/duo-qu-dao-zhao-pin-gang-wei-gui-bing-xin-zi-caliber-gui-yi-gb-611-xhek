"""幂等 seed：3 账号 / 4 渠道 / 160 条原始岗位 / 1 次归并运行 / 3 条历史复核结论。

自然键 upsert（重复执行不新增、不覆盖人工改过的复核状态）：
  users.email
  channels.code
  posts(channel_id, external_id)
  runs.seed_key
  clusters(run_id, fingerprint)
  reviews.seed_key
  audit_logs.seed_key

SEED_SUMMARY 这一行在连续两次运行中逐字一致：
  sources=渠道数 / runs=归并运行数 / findings=归并簇数 / pending=待复核簇数
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.models.run import Run
from src.models.user import User
from src.services import review_service, run_service
from src.services.normalize_service import enrich_post_fields
from src.utils.security import hash_password

from scripts.demo_config import (
    ANCHOR,
    CHANNELS,
    DEMO_PASSWORD,
    DEMO_USERS,
    ORG,
    POSTS,
    SEED_REVIEWS,
    SEED_RUNS,
)


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
        else:
            # 展示名与组织属于 seed 口径（非人工编辑状态），允许纠正
            user.display_name = display_name
            user.role = role
            user.org = ORG
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_channels(db) -> int:
    for spec in CHANNELS:
        channel = db.scalar(select(Channel).where(Channel.code == spec["code"]))
        if channel is None:
            channel = Channel(
                code=spec["code"],
                name=spec["name"],
                kind=spec["kind"],
                crawl_cron=spec["crawl_cron"],
                endpoint=spec.get("endpoint"),
                owner=ORG,
                note=spec.get("note"),
                enabled=True,
                last_crawled_at=ANCHOR - timedelta(hours=spec["crawl_offset_hours"]),
            )
            db.add(channel)
            db.flush()
    return db.scalar(select(func.count()).select_from(Channel)) or 0


def ensure_posts(db) -> int:
    channels = {channel.code: channel for channel in db.scalars(select(Channel)).all()}
    for spec in POSTS:
        channel = channels.get(spec["channel_code"])
        if channel is None:
            continue
        derived = enrich_post_fields(
            company_raw=spec["company_raw"],
            title_raw=spec["title_raw"],
            city=spec["city"],
            salary_raw=spec["salary_raw"],
            degree=spec["degree"],
            experience=spec["experience"],
        )
        post = db.scalar(
            select(Post).where(Post.channel_id == channel.id, Post.external_id == spec["external_id"])
        )
        if post is None:
            post = Post(
                channel_id=channel.id,
                external_id=spec["external_id"],
                seed_key=spec["seed_key"],
            )
            db.add(post)
        post.company_raw = spec["company_raw"]
        post.company_norm = derived["company_norm"]
        post.title_raw = spec["title_raw"]
        post.title_stem = derived["title_stem"]
        post.city = spec["city"]
        post.salary_raw = spec["salary_raw"]
        post.salary_status = derived["salary_status"]
        post.salary_low = derived["salary_low"]
        post.salary_high = derived["salary_high"]
        post.months = derived["months"]
        post.monthly_low = derived["monthly_low"]
        post.monthly_high = derived["monthly_high"]
        post.monthly_median = derived["monthly_median"]
        post.salary_basis = derived["salary_basis"]
        post.salary_confidence = derived["salary_confidence"]
        post.degree = derived["degree"]
        post.experience = derived["experience"]
        post.published_at = spec["published_at"]
        post.expire_at = spec["expire_at"]
        post.raw_text = spec["raw_text"]
    db.flush()
    for code, channel in channels.items():
        spec = next(item for item in CHANNELS if item["code"] == code)
        channel.last_crawled_at = ANCHOR - timedelta(hours=spec["crawl_offset_hours"])
    db.flush()
    return db.scalar(select(func.count()).select_from(Post)) or 0


def ensure_run(db) -> Run:
    for spec in SEED_RUNS:
        run = db.scalar(select(Run).where(Run.seed_key == spec["seed_key"]))
        if run is not None:
            existing_clusters = db.scalar(
                select(func.count()).select_from(Cluster).where(Cluster.run_id == run.id)
            ) or 0
            if existing_clusters:
                return run
            run_service.execute_run(db, run)
            return run
        return run_service.create_and_execute(
            db,
            trigger=spec["trigger"],
            operator_email=spec["operator"],
            threshold=spec["threshold"],
            seed_key=spec["seed_key"],
        )
    raise RuntimeError("SEED_RUNS 为空")


def ensure_reviews(db, run: Run) -> int:
    clusters = db.scalars(
        select(Cluster)
        .where(Cluster.run_id == run.id, Cluster.needs_review.is_(True))
        .order_by(Cluster.fingerprint)
    ).all()
    for index, seed in enumerate(SEED_REVIEWS):
        seed_key = f"seed-review-{index + 1}"
        exists = db.scalar(select(Review).where(Review.seed_key == seed_key))
        if exists is not None:
            continue
        if index >= len(clusters):
            break
        review_service.upsert_decision(
            db,
            cluster_id=clusters[index].id,
            decision=seed["decision"],
            note=seed["note"],
            reviewer=seed["reviewer"],
            seed_key=seed_key,
        )
    db.flush()
    return db.scalar(select(func.count()).select_from(Review)) or 0


def ensure_audit(db) -> None:
    seeds = [
        ("seed-audit-1", "admin@jobmerge.io", "admin", "channel.create", "channel", {"code": "zhaopin"}),
        ("seed-audit-2", "admin@jobmerge.io", "admin", "run.create", "run", {"run": "seed-run-merge-1"}),
        ("seed-audit-3", "analyst@jobmerge.io", "analyst", "review.create", "cluster", {"decision": "merge"}),
    ]
    for seed_key, email, role, action, entity, detail in seeds:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    with session_scope() as db:
        users = ensure_users(db)
        channels = ensure_channels(db)
        posts = ensure_posts(db)
        run = ensure_run(db)
        ensure_reviews(db, run)
        ensure_audit(db)
        runs = db.scalar(select(func.count()).select_from(Run)) or 0
        clusters = db.scalar(
            select(func.count()).select_from(Cluster).where(Cluster.run_id == run.id)
        ) or 0
        pending = review_service.pending_total(db)
        summary = (
            f"SEED_SUMMARY brand=jobmerge users={users} sources={channels} "
            f"runs={runs} findings={clusters} pending={pending}"
        )
        print(summary, flush=True)
        return {
            "users": users,
            "channels": channels,
            "posts": posts,
            "runs": runs,
            "clusters": clusters,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()

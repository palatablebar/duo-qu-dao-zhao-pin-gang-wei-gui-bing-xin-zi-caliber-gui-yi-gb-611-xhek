"""发布口径服务：把复核结论固化成客户可检索的岗位版本。

核心约定（与 `constants/publish_rules.py` 一致）：

- 一个归并簇只有「无需复核」或「已审核通过（merge / keep）」才发布；
- 结论为 split 的簇不再发布合并行，改为簇内每条原始岗位各自发布一行；
- 需要复核但尚无结论的簇只计入待复核，不进入版本明细；
- 过期岗位发布为 withdrawn（保留在版本里可核对，但客户看不到）；
- 发布口径签名（规则版本 + 阈值 + 审核要求）或簇/复核状态变化时生成新版本，
  旧版本标记 superseded，客户入口与导出在同一时刻切到新版本。
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import DEGREE_LABELS, EXPERIENCE_LABELS, ReviewDecision
from src.constants.publish_rules import (
    review_signature,
    rule_signature,
    rule_version,
)
from src.models.channel import Channel
from src.models.audit import AuditLog
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.publication import Publication, PublicationItem
from src.models.review import Review
from src.models.run import Run
from src.services import audit_service
from src.utils.masking import mask_company
from src.utils.timeutil import iso_utc, utcnow

PUBLISHED = "published"
WITHDRAWN = "withdrawn"
RUN_READY_STATUSES = ("success", "partial")


# ---------------------------------------------------------------------------
# 取得当前应该发布的运行
# ---------------------------------------------------------------------------
def target_run(db: Session) -> Run | None:
    """最近一次产出过簇的成功运行。

    严格取「有簇且状态 success/partial」的最近运行：失败的运行不会把客户清单清空；
    完全没有任何可用运行时返回 None（空版本），而不是退回一个失败运行。
    """
    run_ids = db.scalars(
        select(Run.id).where(Run.status.in_(RUN_READY_STATUSES)).order_by(Run.id.desc())
    ).all()
    for run_id in run_ids:
        count = db.scalar(
            select(func.count()).select_from(Cluster).where(Cluster.run_id == run_id)
        ) or 0
        if count:
            return db.get(Run, run_id)
    return None


def active_publication(db: Session) -> Publication | None:
    """当前生效版本；历史上若出现多个 active（并发构建），只认最新的一个。"""
    rows = db.scalars(
        select(Publication).where(Publication.status == "active").order_by(Publication.id.desc())
    ).all()
    if not rows:
        return None
    for stale in rows[1:]:
        stale.status = "superseded"
        stale.superseded_at = utcnow()
    return rows[0]


# ---------------------------------------------------------------------------
# 版本状态指纹
# ---------------------------------------------------------------------------
def _is_expired(moment: datetime | None, now: datetime) -> bool:
    return moment is not None and moment < now


def _state_hash(db: Session, run: Run | None, signature: str) -> str:
    now = utcnow()
    parts: list[str] = [f"rule={signature}", f"run={run.id if run else 0}"]
    if run is None:
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    clusters = db.scalars(select(Cluster).where(Cluster.run_id == run.id).order_by(Cluster.id)).all()
    cluster_ids = [cluster.id for cluster in clusters]
    reviews: dict[int, Review] = {}
    if cluster_ids:
        for review in db.scalars(select(Review).where(Review.cluster_id.in_(cluster_ids))).all():
            reviews[review.cluster_id] = review
    split_member_ids: set[int] = set()
    for cluster in clusters:
        review = reviews.get(cluster.id)
        effective = review if review is not None and review.rule_signature == review_signature() else None
        expired = _is_expired(cluster.expire_at, now) or cluster.status == "expired"
        parts.append(
            "C|{id}|{status}|{nr}|{exp}|{mc}|{dec}|{rid}|{upd}|{sig}".format(
                id=cluster.id,
                status=cluster.status,
                nr=int(cluster.needs_review),
                exp=int(expired),
                mc=cluster.member_count,
                dec=effective.decision if effective else "-",
                rid=effective.id if effective else 0,
                upd=effective.updated_at.isoformat() if effective and effective.updated_at else "-",
                sig=effective.rule_signature if effective else "-",
            )
        )
        if effective is not None and effective.decision == ReviewDecision.SPLIT.value:
            split_member_ids.update(int(item) for item in (cluster.member_ids or []))
    if split_member_ids:
        for post in db.scalars(
            select(Post).where(Post.id.in_(sorted(split_member_ids))).order_by(Post.id)
        ).all():
            parts.append(f"P|{post.id}|{int(_is_expired(post.expire_at, now))}|{post.salary_status}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 版本构建
# ---------------------------------------------------------------------------
def _salary_status(cluster: Cluster, golden: Post | None) -> str:
    if golden is not None:
        return golden.salary_status
    if cluster.monthly_median is not None:
        return "parsed"
    return "negotiable"


def _withdraw_reason(expired: bool) -> str:
    return "expired" if expired else "withdrawn"


def _build(
    db: Session,
    run: Run | None,
    *,
    signature: str,
    state_hash: str,
    reason: str,
    actor: str,
    seed_key: str | None = None,
) -> Publication:
    now = utcnow()
    for old in db.scalars(select(Publication).where(Publication.status == "active")).all():
        old.status = "superseded"
        old.superseded_at = now

    version_no = (db.scalar(select(func.max(Publication.version_no))) or 0) + 1
    publication = Publication(
        version_no=version_no,
        run_id=run.id if run else None,
        status="active",
        rule_version=rule_version(),
        rule_signature=signature,
        state_hash=state_hash,
        threshold=float(run.threshold or 0.0) if run else 0.0,
        reason=reason,
        created_by=actor,
        seed_key=seed_key,
    )
    db.add(publication)
    db.flush()

    clusters = (
        db.scalars(select(Cluster).where(Cluster.run_id == run.id).order_by(Cluster.id)).all()
        if run
        else []
    )
    cluster_ids = [cluster.id for cluster in clusters]
    reviews: dict[int, Review] = {}
    if cluster_ids:
        for review in db.scalars(select(Review).where(Review.cluster_id.in_(cluster_ids))).all():
            reviews[review.cluster_id] = review

    member_ids = sorted({int(item) for cluster in clusters for item in (cluster.member_ids or [])})
    posts: dict[int, Post] = {}
    channel_codes: dict[int, str] = {}
    if member_ids:
        for post in db.scalars(select(Post).where(Post.id.in_(member_ids))).all():
            posts[post.id] = post
        channel_ids = {post.channel_id for post in posts.values()}
        for channel in db.scalars(select(Channel).where(Channel.id.in_(channel_ids))).all():
            channel_codes[channel.id] = channel.code

    pending = split_clusters = 0
    published_clusters = published_posts = 0
    withdrawn_clusters = withdrawn_posts = 0
    expired_items = 0
    ordinal = 0

    def add_item(**fields) -> None:
        nonlocal ordinal
        ordinal += 1
        db.add(
            PublicationItem(
                publication_id=publication.id,
                ordinal=ordinal,
                **fields,
            )
        )

    # 稳定的对外顺序：多成员优先，再按公司/职位/簇 ID。
    ordered = sorted(
        clusters,
        key=lambda row: (-row.member_count, row.company_norm, row.title_stem, row.fingerprint, row.id),
    )
    for cluster in ordered:
        review = reviews.get(cluster.id)
        if review is not None and review.rule_signature != review_signature():
            # 规则变化后旧结论只作为历史记录，不参与发布；簇重新排队复核。
            review = None
        decision = review.decision if review else None
        golden = posts.get(int(cluster.golden_post_id)) if cluster.golden_post_id else None

        def _cluster_item_fields(status: str, withdraw_reason: str) -> dict:
            return {
                "public_id": f"C{cluster.id}",
                "source_kind": "cluster",
                "cluster_id": cluster.id,
                "post_id": cluster.golden_post_id,
                "review_id": review.id if review else None,
                "decision": decision,
                "status": status,
                "withdraw_reason": withdraw_reason,
                "company_display": cluster.company_display,
                "company_norm": cluster.company_norm,
                "title_display": cluster.title_display,
                "title_stem": cluster.title_stem,
                "city": cluster.city,
                "salary_status": _salary_status(cluster, golden),
                "salary_low": cluster.salary_low,
                "salary_high": cluster.salary_high,
                "monthly_median": cluster.monthly_median,
                "salary_basis": cluster.salary_basis or "",
                "months": golden.months if golden else 12,
                "degree": cluster.degree,
                "experience": cluster.experience,
                "published_at": cluster.published_at,
                "expire_at": cluster.expire_at,
                "channels": cluster.channels or [],
                "channel_count": cluster.channel_count,
                "member_count": cluster.member_count,
                "dup_removed": cluster.dup_removed,
                "needs_review": cluster.needs_review,
                "confidence": round(cluster.confidence or 0.0, 3),
            }

        # 1) 拆分结论：原合并行不再发布，簇内每条原始岗位按自己的过期状态独立发布。
        if decision == ReviewDecision.SPLIT.value:
            split_clusters += 1
            for member_id in sorted(int(item) for item in (cluster.member_ids or [])):
                post = posts.get(member_id)
                if post is None:
                    continue
                expired = _is_expired(post.expire_at, now)
                if expired:
                    withdrawn_posts += 1
                    expired_items += 1
                else:
                    published_posts += 1
                channel_code = channel_codes.get(post.channel_id, "")
                add_item(
                    public_id=f"P{post.id}",
                    source_kind="post",
                    cluster_id=cluster.id,
                    post_id=post.id,
                    review_id=review.id if review else None,
                    decision=decision,
                    status=WITHDRAWN if expired else PUBLISHED,
                    withdraw_reason=_withdraw_reason(expired),
                    company_display=post.company_raw,
                    company_norm=post.company_norm,
                    title_display=post.title_raw,
                    title_stem=post.title_stem,
                    city=post.city,
                    salary_status=post.salary_status,
                    salary_low=post.monthly_low,
                    salary_high=post.monthly_high,
                    monthly_median=post.monthly_median,
                    salary_basis=post.salary_basis or "",
                    months=post.months,
                    degree=post.degree,
                    experience=post.experience,
                    published_at=post.published_at,
                    expire_at=post.expire_at,
                    channels=[channel_code] if channel_code else [],
                    channel_count=1,
                    member_count=1,
                    dup_removed=0,
                    needs_review=False,
                    confidence=round(post.salary_confidence or 0.0, 3),
                )
            continue

        # 2) 过期：无论是否复核过都不进客户清单，保留在版本内计入「已撤回」。
        if _is_expired(cluster.expire_at, now) or cluster.status == "expired":
            withdrawn_clusters += 1
            expired_items += 1
            add_item(**_cluster_item_fields(WITHDRAWN, "expired"))
            continue

        # 3) 待复核：需要人工复核但尚无当前规则下的结论，只在内部计数，不进客户清单。
        if review is None and cluster.needs_review:
            pending += 1
            continue

        # 4) 已审核通过（merge / keep）或无需复核：发布合并行。
        published_clusters += 1
        add_item(**_cluster_item_fields(PUBLISHED, ""))

    publication.clusters_total = len(clusters)
    publication.pending_count = pending
    publication.split_count = split_clusters
    publication.published_cluster_count = published_clusters
    publication.published_post_count = published_posts
    publication.withdrawn_cluster_count = withdrawn_clusters
    publication.withdrawn_post_count = withdrawn_posts
    publication.published_count = published_clusters + published_posts
    publication.withdrawn_count = withdrawn_clusters + withdrawn_posts
    publication.expired_count = expired_items
    db.flush()
    return publication


def _reason_for(active: Publication | None, run: Run | None, signature: str) -> str:
    if active is None:
        return "initial"
    if active.rule_signature != signature:
        return "rules"
    if active.run_id != (run.id if run else None):
        return "run"
    return "state"


def ensure_current(
    db: Session,
    *,
    actor: str = "system",
    seed_key: str | None = None,
    commit: bool = True,
) -> Publication:
    """确保存在与当前运行 / 复核结论 / 规则一致的发布版本。

    - 签名或状态未变：直接复用 active 版本（不产生新版本）；
    - 规则版本、阈值、复核结论、过期状态变化：生成新版本并让旧版本立即失效。
    """
    run = target_run(db)
    signature = rule_signature(run.threshold if run else 0.0)
    state_hash = _state_hash(db, run, signature)
    active = active_publication(db)
    if (
        active is not None
        and active.rule_signature == signature
        and active.state_hash == state_hash
        and active.run_id == (run.id if run else None)
    ):
        return active

    reason = _reason_for(active, run, signature)
    # seed_key 是幂等键：同一 seed 批次重复构建时不再占用，避免唯一约束冲突。
    if seed_key and db.scalar(select(Publication).where(Publication.seed_key == seed_key)):
        seed_key = None
    publication = _build(
        db,
        run,
        signature=signature,
        state_hash=state_hash,
        reason=reason,
        actor=actor,
        seed_key=seed_key,
    )
    audit_seed_key = f"{seed_key}-audit" if seed_key else None
    if audit_seed_key and db.scalar(select(AuditLog).where(AuditLog.seed_key == audit_seed_key)):
        audit_seed_key = None
    audit_service.record(
        db,
        actor_email=actor,
        actor_role="system" if actor == "system" else "admin",
        action="publication.build",
        entity="publication",
        entity_id=publication.id,
        detail={
            "version_no": publication.version_no,
            "reason": reason,
            "rule_signature": signature,
            "run_id": publication.run_id,
            "published": publication.published_count,
            "withdrawn": publication.withdrawn_count,
            "pending": publication.pending_count,
        },
        layer="domain",
        seed_key=audit_seed_key,
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return publication


# ---------------------------------------------------------------------------
# 序列化：内部视图 / 客户视图
# ---------------------------------------------------------------------------
def serialize_header(publication: Publication, run: Run | None = None) -> dict:
    return {
        "id": publication.id,
        "version_no": publication.version_no,
        "status": publication.status,
        "run_id": publication.run_id,
        "run_no": run.run_no if run else None,
        "rule_version": publication.rule_version,
        "rule_signature": publication.rule_signature,
        "threshold": round(publication.threshold or 0.0, 3),
        "reason": publication.reason,
        "clusters_total": publication.clusters_total,
        "pending_count": publication.pending_count,
        "split_count": publication.split_count,
        "published_count": publication.published_count,
        "withdrawn_count": publication.withdrawn_count,
        "expired_count": publication.expired_count,
        "created_by": publication.created_by,
        "created_at": iso_utc(publication.created_at),
        "superseded_at": iso_utc(publication.superseded_at),
    }


def serialize_item(item: PublicationItem, *, viewer: bool) -> dict:
    company = mask_company(item.company_display) if viewer else item.company_display
    payload = {
        "id": item.id,
        "public_id": item.public_id,
        "ordinal": item.ordinal,
        "source_kind": item.source_kind,
        "status": item.status,
        "withdraw_reason": item.withdraw_reason,
        "company_display": company,
        "title_display": item.title_display,
        "city": item.city,
        "salary_status": item.salary_status,
        "salary_low": item.salary_low,
        "salary_high": item.salary_high,
        "monthly_median": item.monthly_median,
        "months": item.months,
        "degree": item.degree,
        "degree_label": DEGREE_LABELS.get(item.degree, item.degree),
        "experience": item.experience,
        "experience_label": EXPERIENCE_LABELS.get(item.experience, item.experience),
        "published_at": iso_utc(item.published_at),
        "expire_at": iso_utc(item.expire_at),
        "channels": item.channels or [],
        "channel_count": item.channel_count,
        "member_count": item.member_count,
        "dup_removed": item.dup_removed,
        "confidence": round(item.confidence or 0.0, 3),
    }
    if not viewer:
        payload.update(
            {
                "publication_id": item.publication_id,
                "cluster_id": item.cluster_id,
                "post_id": item.post_id,
                "review_id": item.review_id,
                "decision": item.decision,
                "company_norm": item.company_norm,
                "title_stem": item.title_stem,
                "salary_basis": item.salary_basis,
                "needs_review": item.needs_review,
                "member_ids": [],
            }
        )
    else:
        # 客户详情只需要「这条发布行代表哪些渠道来稿」，不暴露内部簇 id / 复核 id。
        payload["source_kind"] = item.source_kind
    return payload


def list_current(
    db: Session,
    *,
    viewer: bool,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    publication = ensure_current(db, actor="system")
    stmt = select(PublicationItem).where(PublicationItem.publication_id == publication.id)
    count_stmt = select(func.count()).select_from(PublicationItem).where(
        PublicationItem.publication_id == publication.id
    )
    if viewer:
        # 客户只读永远只看 published；显式要求其他状态时返回空，而不是偷偷放宽。
        if status and status != PUBLISHED:
            stmt = stmt.where(False)
            count_stmt = count_stmt.where(False)
        else:
            stmt = stmt.where(PublicationItem.status == PUBLISHED)
            count_stmt = count_stmt.where(PublicationItem.status == PUBLISHED)
    elif status:
        stmt = stmt.where(PublicationItem.status == status)
        count_stmt = count_stmt.where(PublicationItem.status == status)
    if q:
        like = f"%{q.strip()}%"
        clause = (
            PublicationItem.company_display.ilike(like)
            | PublicationItem.title_display.ilike(like)
            | PublicationItem.public_id.ilike(like)
        )
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(PublicationItem.ordinal, PublicationItem.id).limit(limit).offset(offset)
    ).all()
    run = db.get(Run, publication.run_id) if publication.run_id else None
    return {
        "publication": serialize_header(publication, run),
        "items": [serialize_item(row, viewer=viewer) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_item(db: Session, item_id: int, *, viewer: bool) -> dict:
    publication = ensure_current(db, actor="system")
    item = db.get(PublicationItem, item_id)
    if item is None or item.publication_id != publication.id:
        from src.utils.errors import not_found

        raise not_found("publication_item", item_id)
    if viewer and item.status != PUBLISHED:
        from src.utils.errors import not_found

        raise not_found("publication_item", item_id)
    payload = serialize_item(item, viewer=viewer)
    if not viewer:
        cluster = db.get(Cluster, item.cluster_id) if item.cluster_id else None
        payload["members"] = []
        if cluster is not None:
            payload["members"] = [
                {
                    "id": post.id,
                    "channel_code": "",
                    "company_raw": post.company_raw,
                    "title_raw": post.title_raw,
                    "city": post.city,
                    "salary_raw": post.salary_raw,
                    "salary_status": post.salary_status,
                    "monthly_low": post.monthly_low,
                    "monthly_high": post.monthly_high,
                    "monthly_median": post.monthly_median,
                    "is_golden": post.id == cluster.golden_post_id,
                }
                for post in db.scalars(
                    select(Post)
                    .where(Post.id.in_([int(v) for v in (cluster.member_ids or [])]))
                    .order_by(Post.id)
                ).all()
            ]
    return payload


def history(db: Session, limit: int = 20) -> dict:
    ensure_current(db, actor="system")
    rows = db.scalars(select(Publication).order_by(Publication.version_no.desc()).limit(limit)).all()
    runs = {run.id: run for run in db.scalars(select(Run)).all()}
    return {
        "items": [serialize_header(row, runs.get(row.run_id)) for row in rows],
        "total": db.scalar(select(func.count()).select_from(Publication)) or 0,
    }


def customer_rows(db: Session) -> tuple[Publication, list[PublicationItem]]:
    """客户清单的唯一定义：当前 active 版本里 status=published 的岗位，按 ordinal 排序。"""
    publication = ensure_current(db, actor="system")
    rows = db.scalars(
        select(PublicationItem)
        .where(
            PublicationItem.publication_id == publication.id,
            PublicationItem.status == PUBLISHED,
        )
        .order_by(PublicationItem.ordinal, PublicationItem.id)
    ).all()
    return publication, rows


def published_states(db: Session, publication: Publication) -> dict[int, str]:
    """cluster_id -> 该簇在当前发布版本里的状态（published / withdrawn）。

    拆分簇没有自己的合并行（明细是 P 行），统一标记为 published（其成员各自发布）。
    不在本版本明细里的簇（待复核）返回 None，由调用方按「待复核」展示。
    """
    rows = db.scalars(
        select(PublicationItem).where(PublicationItem.publication_id == publication.id)
    ).all()
    states: dict[int, str] = {}
    for row in rows:
        if not row.cluster_id:
            continue
        if row.source_kind == "cluster":
            states[row.cluster_id] = row.status
        else:
            states.setdefault(row.cluster_id, PUBLISHED)
    return states

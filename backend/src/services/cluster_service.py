"""归并簇服务：内部列表/详情（成员对照 + 相似度）、客户可发布视图（脱敏）。

同一套数据，两种口径：

- 内部（admin / analyst）：看本次归并的全部簇与复核状态，用于核对「待复核 / 可发布 / 已撤回」；
- 客户（viewer）：只看当前发布版本里 `published` 的岗位行。拆分簇在这里表现为
  多条独立岗位，未复核簇、精确公司名、内部薪资依据都不会出现。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CLUSTER_STATUS_LABELS,
    DEGREE_LABELS,
    EXPERIENCE_LABELS,
    PARSE_STATUS_LABELS,
    Role,
)
from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.publication import PublicationItem
from src.models.review import Review
from src.services import dedupe, publication_service
from src.services.publication_service import PUBLISHED
from src.utils.masking import mask_company, mask_text
from src.utils.errors import AppError
from src.models.run import Run
from src.utils.timeutil import iso_utc


def _viewer(role: str) -> bool:
    return role == Role.VIEWER.value


def serialize(
    cluster: Cluster,
    role: str,
    review: Review | None = None,
    publish_state: str | None = None,
) -> dict:
    viewer = _viewer(role)
    company = mask_company(cluster.company_display) if viewer else cluster.company_display
    return {
        "id": cluster.id,
        "public_id": f"C{cluster.id}",
        "run_id": cluster.run_id,
        "fingerprint": cluster.fingerprint,
        "blocking_key": cluster.blocking_key,
        "company_display": company,
        "company_norm": cluster.company_norm,
        "title_display": cluster.title_display,
        "title_stem": cluster.title_stem,
        "city": cluster.city,
        "salary_low": cluster.salary_low,
        "salary_high": cluster.salary_high,
        "monthly_median": cluster.monthly_median,
        "salary_basis": cluster.salary_basis,
        "channels": cluster.channels or [],
        "channel_count": cluster.channel_count,
        "member_count": cluster.member_count,
        "dup_removed": cluster.dup_removed,
        "degree": cluster.degree,
        "degree_label": DEGREE_LABELS.get(cluster.degree, cluster.degree),
        "experience": cluster.experience,
        "experience_label": EXPERIENCE_LABELS.get(cluster.experience, cluster.experience),
        "published_at": iso_utc(cluster.published_at),
        "expire_at": iso_utc(cluster.expire_at),
        "status": cluster.status,
        "status_label": CLUSTER_STATUS_LABELS.get(cluster.status, cluster.status),
        "publish_state": publish_state,
        "confidence": round(cluster.confidence, 3),
        "needs_review": cluster.needs_review,
        "review_reason": cluster.review_reason or "",
        "golden_post_id": cluster.golden_post_id,
        "member_ids": cluster.member_ids or [],
        "review": {
            "decision": review.decision,
            "reviewer": review.reviewer,
            "note": review.note,
            "updated_at": iso_utc(review.updated_at),
        }
        if review
        else None,
        "created_at": iso_utc(cluster.created_at),
    }


def _publication_row(item, *, viewer: bool) -> dict:
    """把发布版本明细转成归并簇表格使用的形状（客户只读视图）。"""
    return {
        "id": item.id,
        "public_id": item.public_id,
        "source_kind": item.source_kind,
        "run_id": None,
        "fingerprint": "",
        "blocking_key": "",
        "company_display": mask_company(item.company_display) if viewer else item.company_display,
        "company_norm": "" if viewer else item.company_norm,
        "title_display": item.title_display,
        "title_stem": "" if viewer else item.title_stem,
        "city": item.city,
        "salary_low": item.salary_low,
        "salary_high": item.salary_high,
        "monthly_median": item.monthly_median,
        "salary_basis": "" if viewer else item.salary_basis,
        "channels": item.channels or [],
        "channel_count": item.channel_count,
        "member_count": item.member_count,
        "dup_removed": item.dup_removed,
        "degree": item.degree,
        "degree_label": DEGREE_LABELS.get(item.degree, item.degree),
        "experience": item.experience,
        "experience_label": EXPERIENCE_LABELS.get(item.experience, item.experience),
        "published_at": iso_utc(item.published_at),
        "expire_at": iso_utc(item.expire_at),
        "status": "active",
        "status_label": "可发布",
        "publish_state": item.status,
        "confidence": round(item.confidence or 0.0, 3),
        "needs_review": False,
        "review_reason": "",
        "golden_post_id": None,
        "member_ids": [],
        "review": None,
        "created_at": None,
    }


def latest_run_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Cluster.run_id)))


def _list_public_view(
    db: Session,
    *,
    role: str,
    status: str | None,
    q: str | None,
    multi_only: bool,
    needs_review: bool | None,
    limit: int,
    offset: int,
) -> dict:
    """客户只读：当前发布版本里可发布的岗位行（拆分簇已展开为多条）。"""
    viewer = _viewer(role)
    publication = publication_service.ensure_current(db, actor="system")
    stmt = select(PublicationItem).where(
        PublicationItem.publication_id == publication.id
    )
    count_stmt = select(func.count()).select_from(PublicationItem).where(
        PublicationItem.publication_id == publication.id
    )
    if viewer:
        stmt = stmt.where(PublicationItem.status == PUBLISHED)
        count_stmt = count_stmt.where(PublicationItem.status == PUBLISHED)
    elif status:
        stmt = stmt.where(PublicationItem.status == status)
        count_stmt = count_stmt.where(PublicationItem.status == status)
    if multi_only:
        stmt = stmt.where(PublicationItem.member_count > 1)
        count_stmt = count_stmt.where(PublicationItem.member_count > 1)
    if viewer and needs_review:
        # 客户视图只有已审核通过的行，不存在待复核项。
        stmt = stmt.where(False)
        count_stmt = count_stmt.where(False)
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
        stmt.order_by(
            PublicationItem.ordinal,
            PublicationItem.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    run = db.get(Run, publication.run_id) if publication.run_id else None
    return {
        "items": [_publication_row(row, viewer=viewer) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "run_id": publication.run_id,
        "publication": publication_service.serialize_header(publication, run),
        "customer_view": True,
    }


def list_clusters(
    db: Session,
    *,
    role: str,
    run_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    multi_only: bool = False,
    needs_review: bool | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    if _viewer(role):
        return _list_public_view(
            db,
            role=role,
            status=status,
            q=q,
            multi_only=multi_only,
            needs_review=needs_review,
            limit=limit,
            offset=offset,
        )
    target_run = run_id or latest_run_id(db)
    stmt = select(Cluster)
    count_stmt = select(func.count()).select_from(Cluster)
    if target_run:
        stmt = stmt.where(Cluster.run_id == target_run)
        count_stmt = count_stmt.where(Cluster.run_id == target_run)
    if status:
        stmt = stmt.where(Cluster.status == status)
        count_stmt = count_stmt.where(Cluster.status == status)
    if multi_only:
        stmt = stmt.where(Cluster.member_count > 1)
        count_stmt = count_stmt.where(Cluster.member_count > 1)
    if needs_review is not None:
        stmt = stmt.where(Cluster.needs_review.is_(needs_review))
        count_stmt = count_stmt.where(Cluster.needs_review.is_(needs_review))
    if q:
        like = f"%{q.strip()}%"
        clause = (
            Cluster.company_display.ilike(like)
            | Cluster.title_display.ilike(like)
            | Cluster.fingerprint.ilike(like)
        )
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Cluster.member_count.desc(), Cluster.id).limit(limit).offset(offset)
    ).all()
    reviews = {review.cluster_id: review for review in db.scalars(select(Review)).all()}
    publication = publication_service.ensure_current(db, actor="system")
    run = db.get(Run, publication.run_id) if publication.run_id else None
    published_states = publication_service.published_states(db, publication)
    return {
        "items": [
            serialize(row, role, reviews.get(row.id), published_states.get(row.id))
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "run_id": target_run,
        "publication": publication_service.serialize_header(publication, run),
    }


def get_cluster(db: Session, cluster_id: int, role: str) -> dict:
    if _viewer(role):
        # 客户视图的 id 是发布版本明细 id（拆分岗位各自独立），不会与内部簇 id 混用。
        payload = publication_service.get_item(db, cluster_id, viewer=True)
        payload["company_norm"] = ""
        payload["title_stem"] = ""
        payload["salary_basis"] = ""
        payload["fingerprint"] = ""
        payload["needs_review"] = False
        payload["review_reason"] = ""
        payload["status"] = "active"
        payload["status_label"] = "可发布"
        payload["members"] = _public_members_for(db, cluster_id, payload.get("source_kind"))
        return payload
    cluster = db.get(Cluster, cluster_id)
    if cluster is None:
        raise AppError("NOT_FOUND", 404, {"entity": "cluster", "id": cluster_id})
    review = db.scalar(select(Review).where(Review.cluster_id == cluster.id))
    publication = publication_service.ensure_current(db, actor="system")
    states = publication_service.published_states(db, publication)
    payload = serialize(cluster, role, review, states.get(cluster.id))
    payload["members"] = _members(db, cluster, role)
    payload["publication"] = publication_service.serialize_header(
        publication,
        db.get(Run, publication.run_id) if publication.run_id else None,
    )
    return payload


def _public_members_for(db: Session, item_id: int, source_kind: str | None) -> list[dict]:
    """客户详情的渠道来稿：合并行展示整簇成员，拆分行的单条岗位只展示自己。"""
    from src.models.publication import PublicationItem

    item = db.get(PublicationItem, item_id)
    if item is None:
        return []
    if item.source_kind == "post":
        ids = [item.post_id] if item.post_id else []
        golden_id = item.post_id
    else:
        cluster = db.get(Cluster, item.cluster_id) if item.cluster_id else None
        ids = [int(value) for value in (cluster.member_ids or [])] if cluster else []
        golden_id = cluster.golden_post_id if cluster else None
    if not ids:
        return []
    channels = {channel.id: channel for channel in db.scalars(select(Channel)).all()}
    return [
        {
            "id": row.id,
            "channel_code": channels[row.channel_id].code if row.channel_id in channels else "",
            "channel_name": channels[row.channel_id].name if row.channel_id in channels else "",
            "company_raw": mask_company(row.company_raw),
            "title_raw": row.title_raw,
            "city": row.city,
            "salary_raw": row.salary_raw,
            "salary_status": row.salary_status,
            "salary_status_label": PARSE_STATUS_LABELS.get(row.salary_status, row.salary_status),
            "monthly_low": row.monthly_low,
            "monthly_high": row.monthly_high,
            "monthly_median": row.monthly_median,
            "months": row.months,
            "degree_label": DEGREE_LABELS.get(row.degree, row.degree),
            "experience_label": EXPERIENCE_LABELS.get(row.experience, row.experience),
            "published_at": iso_utc(row.published_at),
            "raw_text": mask_text(row.raw_text, row.company_raw),
            "is_golden": row.id == golden_id,
            "similarity": {"score": 1.0 if row.id == golden_id else 0.0},
        }
        for row in db.scalars(select(Post).where(Post.id.in_(ids)).order_by(Post.id)).all()
    ]


def _members(db: Session, cluster: Cluster, role: str) -> list[dict]:
    ids = [int(item) for item in (cluster.member_ids or [])]
    if not ids:
        return []
    rows = db.scalars(select(Post).where(Post.id.in_(ids)).order_by(Post.id)).all()
    channels = {channel.id: channel for channel in db.scalars(select(Channel)).all()}
    viewer = _viewer(role)
    prepared = []
    for row in rows:
        channel = channels.get(row.channel_id)
        prepared.append(
            {
                "id": row.id,
                "external_id": row.external_id,
                "channel_code": channel.code if channel else "",
                "channel_name": channel.name if channel else "",
                "company_raw": mask_company(row.company_raw) if viewer else row.company_raw,
                "title_raw": row.title_raw,
                "city": row.city,
                "salary_raw": row.salary_raw,
                "salary_status": row.salary_status,
                "salary_status_label": PARSE_STATUS_LABELS.get(row.salary_status, row.salary_status),
                "monthly_low": row.monthly_low,
                "monthly_high": row.monthly_high,
                "monthly_median": row.monthly_median,
                "months": row.months,
                "degree_label": DEGREE_LABELS.get(row.degree, row.degree),
                "experience_label": EXPERIENCE_LABELS.get(row.experience, row.experience),
                "published_at": iso_utc(row.published_at),
                "raw_text": mask_text(row.raw_text, row.company_raw) if viewer else row.raw_text,
                "is_golden": row.id == cluster.golden_post_id,
                "company_norm": row.company_norm,
                "title_stem": row.title_stem,
                "monthly_low_value": row.monthly_low,
                "monthly_high_value": row.monthly_high,
                "monthly_median_value": row.monthly_median,
                "degree": row.degree,
                "experience": row.experience,
            }
        )

    golden = next((item for item in prepared if item["is_golden"]), prepared[0])
    for item in prepared:
        scored = dedupe.similarity(item, golden)
        item["similarity"] = scored
        for key in ("monthly_low_value", "monthly_high_value", "monthly_median_value"):
            item.pop(key, None)
    return prepared

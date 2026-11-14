"""发布口径端到端：复核结论 → 可发布岗位、客户视图、导出与版本切换。"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.models.run import Run
from src.services import (
    cluster_service,
    export_service,
    publication_service,
    review_service,
)
from src.services.normalize_service import enrich_post_fields

NOW = datetime(2026, 11, 14, 9, 30)


def _post(channel: Channel, *, ext: str, company: str, title: str, salary: str, city: str = "北京",
          expired: bool = False) -> Post:
    derived = enrich_post_fields(
        company_raw=company, title_raw=title, city=city, salary_raw=salary,
        degree="本科", experience="3-5年",
    )
    return Post(
        channel_id=channel.id,
        external_id=ext,
        company_raw=company,
        company_norm=derived["company_norm"],
        title_raw=title,
        title_stem=derived["title_stem"],
        city=city,
        salary_raw=salary,
        salary_status=derived["salary_status"],
        salary_low=derived["salary_low"],
        salary_high=derived["salary_high"],
        months=derived["months"],
        monthly_low=derived["monthly_low"],
        monthly_high=derived["monthly_high"],
        monthly_median=derived["monthly_median"],
        salary_basis=derived["salary_basis"],
        salary_confidence=derived["salary_confidence"],
        degree=derived["degree"],
        experience=derived["experience"],
        published_at=NOW - timedelta(days=3),
        expire_at=NOW - timedelta(days=1) if expired else NOW + timedelta(days=30),
        raw_text=f"{company} 招聘 {title}",
    )


def _seed_three_way_duplicate(db):
    channel_a = Channel(code="a", name="渠道 A", kind="site")
    channel_b = Channel(code="b", name="渠道 B", kind="api")
    channel_c = Channel(code="c", name="渠道 C", kind="site")
    db.add_all([channel_a, channel_b, channel_c])
    db.flush()
    posts = [
        _post(channel_a, ext="a1", company="云雀数智科技有限公司", title="Java开发工程师", salary="10-15K"),
        _post(channel_b, ext="b1", company="云雀数智科技有限公司", title="Java开发工程师", salary="10-15K"),
        _post(channel_c, ext="c1", company="云雀数智科技有限公司", title="Java开发工程师", salary="10-15K"),
    ]
    db.add_all(posts)
    db.flush()
    return posts


def _run_merge(db, posts, *, threshold=0.82, fingerprint="fp-1"):
    from src.services import dedupe

    run = Run(run_no="M-TEST-0001", trigger="manual", status="success", operator_email="analyst@x.io",
              threshold=threshold)
    db.add(run)
    db.flush()
    payloads = [
        {
            "id": p.id, "channel_id": p.channel_id, "channel_code": None, "company_raw": p.company_raw,
            "company_norm": p.company_norm, "title_raw": p.title_raw, "title_stem": p.title_stem,
            "city": p.city, "salary_raw": p.salary_raw, "monthly_low": p.monthly_low,
            "monthly_high": p.monthly_high, "monthly_median": p.monthly_median, "months": p.months,
            "degree": p.degree, "experience": p.experience, "published_at": p.published_at,
            "expire_at": p.expire_at, "raw_text": p.raw_text,
        }
        for p in posts
    ]
    result = dedupe.build_clusters(payloads, threshold=threshold, now=NOW)
    cluster_data = result["clusters"][0]
    cluster = Cluster(
        run_id=run.id,
        fingerprint=fingerprint,
        blocking_key=cluster_data["blocking_key"],
        company_norm=cluster_data["company_norm"],
        company_display=cluster_data["company_display"],
        title_stem=cluster_data["title_stem"],
        title_display=cluster_data["title_display"],
        city=cluster_data["city"],
        salary_low=cluster_data["salary_low"],
        salary_high=cluster_data["salary_high"],
        monthly_median=cluster_data["monthly_median"],
        salary_basis=cluster_data["salary_basis"],
        member_ids=cluster_data["member_ids"],
        channels=cluster_data["channels"],
        channel_count=cluster_data["channel_count"],
        member_count=cluster_data["member_count"],
        dup_removed=cluster_data["dup_removed"],
        degree=cluster_data["degree"],
        experience=cluster_data["experience"],
        published_at=cluster_data["published_at"],
        expire_at=cluster_data["expire_at"],
        status=cluster_data["status"],
        confidence=cluster_data["confidence"],
        needs_review=True,
        review_reason="公司名写法不一致",
        golden_post_id=cluster_data["golden_post_id"],
    )
    db.add(cluster)
    db.flush()
    return run, cluster


def test_needs_review_cluster_is_not_published_until_reviewed(db):
    posts = _seed_three_way_duplicate(db)
    run, cluster = _run_merge(db, posts)

    publication = publication_service.ensure_current(db, actor="analyst@x.io")
    assert publication.pending_count == 1
    assert publication.published_count == 0

    _header, customer_rows = publication_service.customer_rows(db)
    assert customer_rows == []

    # 客户视图为空，且不会暴露未复核簇。
    viewer_list = cluster_service.list_clusters(db, role="viewer")
    assert viewer_list["total"] == 0


def test_approved_cluster_publishes_and_split_creates_independent_rows(db):
    posts = _seed_three_way_duplicate(db)
    run, cluster = _run_merge(db, posts)

    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="merge", note="同一岗位", reviewer="analyst@x.io"
    )
    publication = publication_service.ensure_current(db, actor="analyst@x.io")
    assert publication.published_count == 1

    viewer_list = cluster_service.list_clusters(db, role="viewer")
    assert viewer_list["total"] == 1
    # 客户视图不含内部字段与精确公司名
    item = viewer_list["items"][0]
    assert "****" in item["company_display"]
    assert item["salary_basis"] == ""
    assert item["company_norm"] == ""

    # 拆分：原合并行消失，三条原始岗位各自发布
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="split", note="实为不同岗位", reviewer="analyst@x.io"
    )
    split_publication = publication_service.ensure_current(db, actor="analyst@x.io")
    assert split_publication.published_count == 3
    assert split_publication.split_count == 1
    split_rows = cluster_service.list_clusters(db, role="viewer")
    assert split_rows["total"] == 3
    ids = [row["public_id"] for row in split_rows["items"]]
    assert len(set(ids)) == 3
    assert all(row["member_count"] == 1 for row in split_rows["items"])


def test_export_matches_customer_list_exactly(db):
    posts = _seed_three_way_duplicate(db)
    _run, cluster = _run_merge(db, posts)
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="merge", note="ok", reviewer="analyst@x.io"
    )
    publication_service.ensure_current(db, actor="analyst@x.io")

    viewer_list = cluster_service.list_clusters(db, role="viewer", limit=200)
    csv_bytes = export_service.clusters_csv(db)
    text = csv_bytes.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    # 表头 1 行 + 与客户列表总量一致
    assert len(lines) == viewer_list["total"] + 1
    assert "云雀数智科技有限公司" not in text  # 精确公司名不外泄
    assert "fp-1" not in text  # 内部指纹不外泄
    assert "【" not in text


def test_viewer_detail_masks_and_split_row_shows_only_itself(db):
    posts = _seed_three_way_duplicate(db)
    _run, cluster = _run_merge(db, posts)
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="merge", note="ok", reviewer="analyst@x.io"
    )
    publication_service.ensure_current(db, actor="analyst@x.io")

    listed = cluster_service.list_clusters(db, role="viewer")
    row = listed["items"][0]
    detail = cluster_service.get_cluster(db, row["id"], "viewer")
    assert len(detail["members"]) == 3
    assert all("****" in member["company_raw"] for member in detail["members"])
    assert detail["company_norm"] == ""
    assert detail["salary_basis"] == ""
    assert detail["fingerprint"] == ""

    # 拆分后每条岗位的客户详情只展示自己那条来稿
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="split", note="独立", reviewer="analyst@x.io"
    )
    publication_service.ensure_current(db, actor="analyst@x.io")
    rows = cluster_service.list_clusters(db, role="viewer")["items"]
    post_row = next(item for item in rows if item["public_id"].startswith("P"))
    split_detail = cluster_service.get_cluster(db, post_row["id"], "viewer")
    assert len(split_detail["members"]) == 1
    assert split_detail["members"][0]["id"] == int(post_row["public_id"][1:])
    assert "****" in split_detail["members"][0]["company_raw"]


def test_rule_version_change_invalidates_old_publish(db, monkeypatch):
    posts = _seed_three_way_duplicate(db)
    _run, cluster = _run_merge(db, posts)
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="merge", note="ok", reviewer="analyst@x.io"
    )
    first = publication_service.ensure_current(db, actor="analyst@x.io")
    assert first.published_count == 1
    assert first.status == "active"

    from src.constants import publish_rules

    monkeypatch.setattr(publish_rules, "REVIEW_RULE_VERSION", "review-rules-v2")
    monkeypatch.setattr(publish_rules, "rule_version", lambda: "review-rules-v2")

    second = publication_service.ensure_current(db, actor="admin@x.io")
    assert second.id != first.id
    assert second.status == "active"
    assert first.status == "superseded"
    # 旧规则下的结论不再算「审核通过」，簇重新排队，客户清单清空
    assert second.published_count == 0
    assert second.pending_count == 1
    stale = db.get(type(first), first.id)
    assert stale.status == "superseded"

    pending = review_service.pending_clusters(db)
    assert pending["total"] == 1


def test_rerun_keeps_review_records(db):
    posts = _seed_three_way_duplicate(db)
    run, cluster = _run_merge(db, posts)
    review_service.upsert_decision(
        db, cluster_id=cluster.id, decision="merge", note="同一岗位", reviewer="analyst@x.io"
    )
    review_count_before = db.query(Review).count()
    assert review_count_before == 1

    # 重算：删掉旧簇（外键 SET NULL，复核行保留）、插入同指纹的新簇
    review_row = db.query(Review).one()
    db.delete(cluster)
    db.flush()
    review_row.cluster_id = None  # 模拟 ON DELETE SET NULL（SQLite 默认不强制外键）
    db.flush()
    new_cluster = Cluster(
        run_id=run.id,
        fingerprint="fp-1",
        blocking_key="k",
        company_norm="云雀数智科技",
        company_display="云雀数智科技有限公司",
        title_stem="java开发工程师",
        title_display="Java开发工程师",
        city="北京",
        member_ids=[p.id for p in posts],
        channels=["a", "b", "c"],
        channel_count=3,
        member_count=3,
        dup_removed=2,
        status="active",
        needs_review=True,
        golden_post_id=posts[0].id,
    )
    db.add(new_cluster)
    db.flush()
    from src.services.merge_service import _reattach_reviews

    attached = _reattach_reviews(db, run)
    assert attached == 1
    review = db.query(Review).one()
    assert review.cluster_id == new_cluster.id
    assert review.decision == "merge"
    assert review.rule_signature  # 结论带规则签名

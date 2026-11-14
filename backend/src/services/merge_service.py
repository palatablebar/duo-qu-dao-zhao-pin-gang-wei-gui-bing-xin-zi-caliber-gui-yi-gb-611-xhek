"""归并运行：读取全部启用渠道的原始岗位 → 算法 A 汇总口径 → 算法 B 聚类 → 落库。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.channel import Channel
from src.models.cluster import Cluster
from src.models.post import Post
from src.models.review import Review
from src.models.run import Run
from src.services import dedupe
from src.utils.timeutil import local_now, local_stamp


def _post_rows(db: Session) -> list[tuple[Post, Channel]]:
    stmt = (
        select(Post, Channel)
        .join(Channel, Post.channel_id == Channel.id)
        .where(Channel.enabled.is_(True))
        .order_by(Post.id)
    )
    return [(post, channel) for post, channel in db.execute(stmt).all()]


def _payload(post: Post, channel: Channel) -> dict:
    return {
        "id": post.id,
        "channel_id": post.channel_id,
        "channel_code": channel.code,
        "channel_name": channel.name,
        "company_raw": post.company_raw,
        "company_norm": post.company_norm,
        "title_raw": post.title_raw,
        "title_stem": post.title_stem,
        "city": post.city,
        "salary_raw": post.salary_raw,
        "monthly_low": post.monthly_low,
        "monthly_high": post.monthly_high,
        "monthly_median": post.monthly_median,
        "months": post.months,
        "degree": post.degree,
        "experience": post.experience,
        "published_at": post.published_at,
        "expire_at": post.expire_at,
        "raw_text": post.raw_text,
    }


CLUSTER_FIELDS = (
    "blocking_key",
    "company_norm",
    "company_display",
    "title_stem",
    "title_display",
    "city",
    "salary_low",
    "salary_high",
    "monthly_median",
    "salary_basis",
    "member_ids",
    "channels",
    "channel_count",
    "member_count",
    "dup_removed",
    "degree",
    "experience",
    "published_at",
    "expire_at",
    "status",
    "confidence",
    "needs_review",
    "review_reason",
    "golden_post_id",
)


def execute_merge(db: Session, run: Run) -> dict:
    rows = _post_rows(db)
    payloads = [_payload(post, channel) for post, channel in rows]
    result = dedupe.build_clusters(payloads, threshold=run.threshold or dedupe.DEFAULT_THRESHOLD)
    clusters = result["clusters"]

    existing = {
        cluster.fingerprint: cluster
        for cluster in db.scalars(select(Cluster).where(Cluster.run_id == run.id)).all()
    }
    for item in clusters:
        cluster = existing.pop(item["fingerprint"], None)
        if cluster is None:
            cluster = Cluster(run_id=run.id, fingerprint=item["fingerprint"])
            db.add(cluster)
        for field in CLUSTER_FIELDS:
            setattr(cluster, field, item[field])
    for leftover in existing.values():
        db.delete(leftover)
    db.flush()
    _reattach_reviews(db, run)

    parsed = sum(1 for post, _ in rows if post.salary_status == "parsed")
    negotiable = sum(1 for post, _ in rows if post.salary_status == "negotiable")
    unparsed_posts = [post for post, _ in rows if post.salary_status == "unparsed"]
    total = len(rows)
    channel_codes = sorted({channel.code for _, channel in rows})

    metrics = {
        "posts_in": total,
        "channels": channel_codes,
        "channel_count": len(channel_codes),
        "parsed": parsed,
        "negotiable": negotiable,
        "unparsed": len(unparsed_posts),
        "parse_fail_rate": round(len(unparsed_posts) / total, 4) if total else 0.0,
        "noncomparable_rate": round((negotiable + len(unparsed_posts)) / total, 4) if total else 0.0,
        "blocks": result["metrics"]["blocks"],
        "pairs": result["metrics"]["pairs"],
        "edges": result["metrics"]["edges"],
        "clusters": result["metrics"]["clusters"],
        "multi_clusters": result["metrics"]["multi_clusters"],
        "dupes_removed": result["metrics"]["dupes_removed"],
        "largest_cluster": result["metrics"]["largest_cluster"],
        "needs_review": result["metrics"]["needs_review"],
        "expired_clusters": result["metrics"]["expired_clusters"],
        "threshold": run.threshold,
        "avg_confidence": round(
            sum(item["confidence"] for item in clusters) / len(clusters), 4
        )
        if clusters
        else 0.0,
        "unparsed_samples": [
            {"raw": post.salary_raw, "reason": (post.salary_basis or "").split("：")[-1][:60]}
            for post in unparsed_posts[:5]
        ],
    }
    log_lines = [
        f"归并运行 {run.run_no} 开始于 {local_stamp(local_now())}，阈值 {run.threshold:.2f}",
        f"输入原始岗位 {total} 条，来自 {len(channel_codes)} 个渠道：{'、'.join(channel_codes)}",
        f"薪资口径：已归一 {parsed} / 面议 {negotiable} / 不可比 {len(unparsed_posts)}"
        f"（不可比占比 {metrics['noncomparable_rate'] * 100:.2f}%）",
        f"分块 {metrics['blocks']} 个，两两比较 {metrics['pairs']} 对，连边 {metrics['edges']} 条",
        f"输出 {metrics['clusters']} 簇（多成员 {metrics['multi_clusters']} 簇，最大 {metrics['largest_cluster']} 条），"
        f"消重 {metrics['dupes_removed']} 条",
        f"待人工复核 {metrics['needs_review']} 簇，已过期 {metrics['expired_clusters']} 簇",
    ]
    status = "success" if total and clusters else "partial"
    return {"metrics": metrics, "log": "\n".join(log_lines), "status": status}


def _reattach_reviews(db: Session, run: Run) -> int:
    """把复核结论按指纹延续到本次运行的新簇上（复核记录不丢、不重复人工）。

    归并重算会为同样的岗位生成新的簇行。复核结论按指纹随版本延续：
    - 结论行本身永不删除（簇被替换时外键 SET NULL，快照字段保留可追溯）；
    - 同指纹的新簇会挂上这条结论，昨天的「合并 / 拆分 / 保持」不用每天重做；
    - 规则版本变化时，结论的 rule_signature 与当前不一致，发布层会忽略它并把簇
      重新排进待复核队列（结论作为历史记录保留）。
    返回重新挂接的条数。
    """
    clusters = {
        cluster.fingerprint: cluster
        for cluster in db.scalars(select(Cluster).where(Cluster.run_id == run.id)).all()
    }
    if not clusters:
        return 0
    # 每个簇最多一条复核结论（uq_reviews_cluster）；先占位再挂接，避免冲突。
    taken = {
        review.cluster_id
        for review in db.scalars(select(Review).where(Review.cluster_id.isnot(None))).all()
        if review.cluster_id in {cluster.id for cluster in clusters.values()}
    }
    attached = 0
    for review in db.scalars(select(Review).order_by(Review.id)).all():
        cluster = clusters.get(review.fingerprint)
        if cluster is None or review.cluster_id == cluster.id or cluster.id in taken:
            continue
        if review.cluster_id is not None:
            current = db.get(Cluster, review.cluster_id)
            if current is not None and current.run_id == run.id:
                # 同一次运行里已有别的簇占用这条结论，不抢。
                continue
        review.cluster_id = cluster.id
        review.run_id = run.id
        taken.add(cluster.id)
        if review.decision == "split":
            cluster.status = "merged"
        elif cluster.status != "expired":
            cluster.status = "active"
        db.flush()
        attached += 1
    return attached

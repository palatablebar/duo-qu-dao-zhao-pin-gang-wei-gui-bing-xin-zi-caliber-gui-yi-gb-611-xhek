"""算法 B｜重复岗归并（纯函数、确定性、不访问网络）。

口径（README §10）：

1. blocking key = `company_norm + city + salary_bucket`，同块内才做两两比较；
2. 相似度 `score = 0.45*title_jaccard + 0.25*company_sim + 0.20*salary_overlap + 0.10*attr_match`；
3. `score >= threshold`（默认 0.82）连边，并查集聚类；
4. golden record 取「字段最全 + 发布最新」；
5. 输出每簇 `member_count / dup_removed / confidence / needs_review`。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from difflib import SequenceMatcher

from src.services.normalize_service import (
    normalize_city,
    normalize_company,
    normalize_title,
    title_tokens,
)

WEIGHTS = {"title": 0.45, "company": 0.25, "salary": 0.20, "attr": 0.10}
DEFAULT_THRESHOLD = 0.82
SALARY_BUCKET_WIDTH = 5000


def salary_bucket(monthly_median: int | None) -> str:
    if monthly_median is None:
        return "na"
    return str(int(monthly_median) // SALARY_BUCKET_WIDTH)


def blocking_key(post: dict) -> str:
    return f"{post['company_norm']}|{post['city']}|{salary_bucket(post.get('monthly_median'))}"


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 4)


def company_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left.startswith(right) or right.startswith(left):
        return 0.92
    return round(SequenceMatcher(None, left, right).ratio(), 4)


def salary_overlap(left: dict, right: dict) -> float:
    l_low, l_high = left.get("monthly_low"), left.get("monthly_high")
    r_low, r_high = right.get("monthly_low"), right.get("monthly_high")
    l_known = l_low is not None and l_high is not None
    r_known = r_low is not None and r_high is not None
    if not l_known and not r_known:
        return 0.6  # 双方都不可比：按同档弱证据处理
    if not l_known or not r_known:
        return 0.0
    intersection = max(0, min(l_high, r_high) - max(l_low, r_low))
    union = max(l_high, r_high) - min(l_low, r_low)
    if union <= 0:
        return 1.0 if l_low == r_low else 0.0
    return round(max(0.0, min(1.0, intersection / union)), 4)


def _attr_pair(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if left == "any" or right == "any":
        return 0.7
    return 0.0


def attr_match(left: dict, right: dict) -> float:
    degree = _attr_pair(left.get("degree", "any"), right.get("degree", "any"))
    experience = _attr_pair(left.get("experience", "any"), right.get("experience", "any"))
    return round(0.5 * degree + 0.5 * experience, 4)


def similarity(left: dict, right: dict) -> dict:
    title = jaccard(title_tokens(left["title_stem"]), title_tokens(right["title_stem"]))
    company = company_similarity(left["company_norm"], right["company_norm"])
    salary = salary_overlap(left, right)
    attr = attr_match(left, right)
    score = (
        WEIGHTS["title"] * title
        + WEIGHTS["company"] * company
        + WEIGHTS["salary"] * salary
        + WEIGHTS["attr"] * attr
    )
    return {
        "title_jaccard": title,
        "company_sim": company,
        "salary_overlap": salary,
        "attr_match": attr,
        "score": round(score, 4),
    }


def _prepare(post: dict) -> dict:
    prepared = dict(post)
    prepared["company_norm"] = post.get("company_norm") or normalize_company(post.get("company_raw", ""))
    prepared["title_stem"] = post.get("title_stem") or normalize_title(post.get("title_raw", ""))
    prepared["city"] = normalize_city(post.get("city", ""))
    prepared.setdefault("degree", "any")
    prepared.setdefault("experience", "any")
    prepared.setdefault("monthly_low", None)
    prepared.setdefault("monthly_high", None)
    prepared.setdefault("monthly_median", None)
    prepared.setdefault("months", 12)
    return prepared


def _completeness(post: dict) -> int:
    score = 0
    for field in ("company_raw", "title_raw", "salary_raw", "raw_text"):
        if post.get(field):
            score += 1
    if post.get("degree", "any") != "any":
        score += 1
    if post.get("experience", "any") != "any":
        score += 1
    if post.get("published_at"):
        score += 1
    if post.get("expire_at"):
        score += 1
    return score


def _published_ts(post: dict) -> float:
    value = post.get("published_at")
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


def pick_golden(members: list[dict]) -> dict:
    """字段最全 → 发布最新 → id 最小（确定性兜底）。"""
    return sorted(
        members,
        key=lambda item: (-_completeness(item), -_published_ts(item), int(item.get("id") or 0)),
    )[0]


def _fingerprint(key: str, title_stem: str) -> str:
    return hashlib.sha1(f"{key}|{title_stem}".encode("utf-8")).hexdigest()[:12]


def _cluster_status(members: list[dict], now: datetime | None) -> str:
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    expiries = [item.get("expire_at") for item in members]
    if all(isinstance(value, datetime) and value < moment for value in expiries):
        return "expired"
    return "active"


def build_clusters(posts: list[dict], threshold: float = DEFAULT_THRESHOLD, now: datetime | None = None) -> dict:
    prepared = [_prepare(post) for post in posts]
    parent: dict[int, int] = {int(item["id"]): int(item["id"]) for item in prepared}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    blocks: dict[str, list[dict]] = {}
    for item in sorted(prepared, key=lambda row: int(row["id"])):
        blocks.setdefault(blocking_key(item), []).append(item)

    pair_scores: dict[tuple[int, int], float] = {}
    pair_count = 0
    edge_count = 0
    for key in sorted(blocks):
        members = blocks[key]
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                pair_count += 1
                scored = similarity(left, right)
                pair_scores[(int(left["id"]), int(right["id"]))] = scored["score"]
                if scored["score"] >= threshold:
                    union(int(left["id"]), int(right["id"]))
                    edge_count += 1

    grouped: dict[int, list[dict]] = {}
    for item in prepared:
        grouped.setdefault(find(int(item["id"])), []).append(item)

    used: set[str] = set()
    clusters: list[dict] = []
    for root in sorted(grouped):
        members = sorted(grouped[root], key=lambda row: int(row["id"]))
        golden = pick_golden(members)
        key = blocking_key(members[0])
        base = _fingerprint(key, members[0]["title_stem"])
        fingerprint = base
        suffix = 1
        while fingerprint in used:
            suffix += 1
            fingerprint = f"{base}-{suffix}"
        used.add(fingerprint)

        scores: list[float] = []
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                score = pair_scores.get((int(left["id"]), int(right["id"])))
                if score is not None:
                    scores.append(score)

        medians = [item["monthly_median"] for item in members if item.get("monthly_median") is not None]
        lows = [item["monthly_low"] for item in members if item.get("monthly_low") is not None]
        highs = [item["monthly_high"] for item in members if item.get("monthly_high") is not None]
        months = {item.get("months", 12) for item in members}
        company_raws = {item.get("company_raw", "") for item in members}
        variants = {item.get("salary_raw", "") for item in members}

        # 只有「发薪月数」或「公司名写法」不一致才需要人工确认；
        # 同一区间换写法（如 10-15K / 月薪10000-15000元）算法已确定等价，不进复核队列。
        needs_review = len(members) > 1 and (len(months) > 1 or len(company_raws) > 1)
        reasons: list[str] = []
        if len(company_raws) > 1:
            reasons.append("公司名写法不一致")
        if len(months) > 1:
            reasons.append("含不同发薪月数写法")
        if needs_review and len(variants) > 1:
            reasons.append(f"{len(variants)} 种薪资写法")
        review_reason = "；".join(reasons) if needs_review else ""

        clusters.append(
            {
                "fingerprint": fingerprint,
                "blocking_key": key,
                "company_norm": members[0]["company_norm"],
                "company_display": golden.get("company_raw") or members[0]["company_norm"],
                "title_stem": members[0]["title_stem"],
                "title_display": golden.get("title_raw") or members[0]["title_stem"],
                "city": members[0]["city"],
                "salary_low": min(lows) if lows else None,
                "salary_high": max(highs) if highs else None,
                "monthly_median": sorted(medians)[len(medians) // 2] if medians else None,
                "salary_basis": " / ".join(sorted(variants)[:3]),
                "channels": sorted({str(item.get("channel_code") or item.get("channel_id")) for item in members}),
                "channel_count": len({str(item.get("channel_code") or item.get("channel_id")) for item in members}),
                "member_count": len(members),
                "dup_removed": len(members) - 1,
                "degree": golden.get("degree", "any"),
                "experience": golden.get("experience", "any"),
                "published_at": max(
                    (item for item in (member.get("published_at") for member in members) if isinstance(item, datetime)),
                    default=None,
                ),
                "expire_at": golden.get("expire_at"),
                "status": _cluster_status(members, now),
                "confidence": round(sum(scores) / len(scores), 3) if scores else 1.0,
                "needs_review": needs_review,
                "review_reason": review_reason,
                "golden_post_id": int(golden["id"]),
                "member_ids": [int(item["id"]) for item in members],
            }
        )

    clusters.sort(key=lambda item: (-item["member_count"], item["company_norm"], item["title_stem"], item["fingerprint"]))
    multi = [item for item in clusters if item["member_count"] > 1]
    metrics = {
        "posts_in": len(prepared),
        "blocks": len(blocks),
        "pairs": pair_count,
        "edges": edge_count,
        "clusters": len(clusters),
        "multi_clusters": len(multi),
        "dupes_removed": sum(item["dup_removed"] for item in clusters),
        "largest_cluster": max((item["member_count"] for item in clusters), default=0),
        "needs_review": sum(1 for item in clusters if item["needs_review"]),
        "expired_clusters": sum(1 for item in clusters if item["status"] == "expired"),
        "threshold": threshold,
    }
    return {"clusters": clusters, "metrics": metrics}

"""接口层：客户视图 / 导出 / 复核写结论后的即时切换（真实 FastAPI + SQLite）。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PASSWORD = "Demo@2026"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每个用例一套独立 SQLite 库，跑真实 seed。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "jobmerge.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    from src.models import Base

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    from src.config import database

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(database, "session_scope", lambda: __import__("contextlib").contextmanager(lambda: (yield)))

    from scripts import seed_demo as seed

    db = Session()
    seed.ensure_users(db)
    seed.ensure_channels(db)
    seed.ensure_posts(db)
    db.flush()
    run = seed.ensure_run(db)
    db.flush()
    seed.ensure_reviews(db, run)
    db.commit()
    db.close()

    from src.config import app as app_module

    application = app_module.create_app()
    with TestClient(application) as test_client:
        yield test_client


def _login(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _csv_rows(response):
    text = response.content.decode("utf-8-sig")
    return [line for line in text.splitlines() if line.strip()]


def test_viewer_sees_only_published_and_export_matches(client):
    viewer = _login(client, "viewer@jobmerge.io")
    admin = _login(client, "admin@jobmerge.io")

    clusters = client.get("/api/clusters", params={"limit": 200}, headers=viewer).json()
    assert clusters["customer_view"] is True
    assert clusters["publication"]["status"] == "active"
    assert len(clusters["items"]) == clusters["total"]
    # 脱敏、无内部字段
    for item in clusters["items"]:
        assert item["company_display"].endswith("（脱敏）") or "****" in item["company_display"]
        assert item["salary_basis"] == ""
        assert item["company_norm"] == ""
        assert item["needs_review"] is False

    exported = client.get("/api/exports/clusters.csv", headers=admin)
    assert exported.status_code == 200
    rows = _csv_rows(exported)
    # 表头 + 与客户列表总量一致
    assert len(rows) == clusters["total"] + 1

    # viewer 导出被拒（403）
    assert client.get("/api/exports/clusters.csv", headers=viewer).status_code == 403


def test_viewer_overview_hides_internal_counts(client):
    viewer = _login(client, "viewer@jobmerge.io")
    admin = _login(client, "admin@jobmerge.io")
    viewer_data = client.get("/api/overview", headers=viewer).json()
    admin_data = client.get("/api/overview", headers=admin).json()

    assert viewer_data["pending_total"] == 0
    assert viewer_data["clusters_total"] == viewer_data["publication"]["published_count"]
    assert viewer_data["clusters_total"] < admin_data["clusters_total"]
    # 内部核对数字只在内部角色出现
    assert admin_data["publish_stats"]["pending"] >= 1
    assert admin_data["publish_stats"]["published"] == viewer_data["clusters_total"]


def test_review_immediately_switches_customer_view_and_export(client):
    viewer = _login(client, "viewer@jobmerge.io")
    analyst = _login(client, "analyst@jobmerge.io")

    before = client.get("/api/clusters", params={"limit": 200}, headers=viewer).json()
    pending = client.get("/api/reviews/pending", params={"limit": 50}, headers=analyst).json()
    assert pending["total"] >= 1
    target = next(row for row in pending["items"] if row["member_count"] > 1)

    response = client.post(
        "/api/reviews",
        json={"cluster_id": target["id"], "decision": "split", "note": "实为不同岗位"},
        headers=analyst,
    )
    assert response.status_code == 201, response.text
    published = response.json()["publication"]

    after = client.get("/api/clusters", params={"limit": 200}, headers=viewer).json()
    assert after["publication"]["version_no"] == published["version_no"]
    # 待复核簇原本不在客户视图里；拆分后簇内成员各自发布，故 +成员数
    assert after["total"] == before["total"] + target["member_count"]
    assert after["publication"]["split_count"] >= 1

    rows = _csv_rows(client.get("/api/exports/clusters.csv", headers=analyst))
    assert len(rows) == after["total"] + 1


def test_viewer_posts_hide_internal_fields(client):
    viewer = _login(client, "viewer@jobmerge.io")
    admin = _login(client, "admin@jobmerge.io")

    listing = client.get("/api/posts", params={"limit": 20}, headers=viewer).json()
    assert listing["items"]
    for item in listing["items"]:
        assert item["company_norm"] == ""
        assert item["salary_basis"] == ""
        # 精确公司名被脱敏
        assert "有限公司" not in item["company_raw"]

    detail = client.get(f"/api/posts/{listing['items'][0]['id']}", headers=viewer).json()
    assert detail["company_norm"] == "" and detail["salary_basis"] == ""

    admin_item = client.get(f"/api/posts/{listing['items'][0]['id']}", headers=admin).json()
    assert admin_item["company_norm"] != ""
    assert admin_item["salary_basis"] != ""


def test_publications_endpoints_match_customer_view(client):
    viewer = _login(client, "viewer@jobmerge.io")
    admin = _login(client, "admin@jobmerge.io")

    current = client.get("/api/publications/current", params={"limit": 200}, headers=viewer).json()
    clusters = client.get("/api/clusters", params={"limit": 200}, headers=viewer).json()
    assert current["total"] == clusters["total"]
    assert {row["public_id"] for row in current["items"]} == {
        row["public_id"] for row in clusters["items"]
    }

    # 客户不能借 status 参数看到已撤回行；内部可以。
    hidden = client.get("/api/publications/current", params={"status": "withdrawn"}, headers=viewer).json()
    assert hidden["total"] == 0
    withdrawn = client.get(
        "/api/publications/current", params={"status": "withdrawn", "limit": 200}, headers=admin
    ).json()
    assert withdrawn["total"] == current["publication"]["withdrawn_count"]

    history = client.get("/api/publications/history", headers=admin).json()
    assert history["items"][0]["status"] == "active"


def test_counts_endpoint_matches_publication(client):
    admin = _login(client, "admin@jobmerge.io")
    counts = client.get("/api/reviews/counts", headers=admin).json()
    publication = counts["publication"]
    # 待复核 + 可发布 + 已撤回（簇 + 拆分岗位）应覆盖本次归并全部簇
    assert publication["run_id"] is not None
    assert counts["pending"] == publication["pending_count"]
    assert publication["clusters_total"] >= 118
    assert publication["published_count"] + publication["pending_count"] + publication["expired_count"] <= \
        publication["clusters_total"] + publication["split_count"] * 3

"""归并簇控制器。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import cluster_service


def list_clusters(db: Session, **filters) -> dict:
    return cluster_service.list_clusters(db, **filters)


def get_cluster(db: Session, cluster_id: int, role: str) -> dict:
    return cluster_service.get_cluster(db, cluster_id, role)

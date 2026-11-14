"""ORM 模型聚合导出（Base 用于 create_all）。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from src.models.user import User  # noqa: E402
from src.models.audit import AuditLog  # noqa: E402
from src.models.channel import Channel  # noqa: E402
from src.models.post import Post  # noqa: E402
from src.models.run import Run  # noqa: E402
from src.models.cluster import Cluster  # noqa: E402
from src.models.review import Review  # noqa: E402
from src.models.publication import Publication, PublicationItem  # noqa: E402

__all__ = [
    "Base",
    "User",
    "AuditLog",
    "Channel",
    "Post",
    "Run",
    "Cluster",
    "Review",
    "Publication",
    "PublicationItem",
]

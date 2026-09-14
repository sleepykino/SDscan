"""SQLAlchemy 引擎、会话与声明式基类。

统一通过 ORM 访问 SQLite，禁止裸 SQL 散落在业务代码中；
数据库 URL 集中在本文件，日后切换 PostgreSQL 只改此处。
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DB_PATH, ensure_dirs

ensure_dirs()

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表并写入种子数据（幂等）。"""
    from . import models  # noqa: F401  确保模型已注册到 metadata
    from .seed import seed_all

    Base.metadata.create_all(bind=engine)
    seed_all()

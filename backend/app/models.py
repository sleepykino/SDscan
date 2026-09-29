"""ORM 模型：对应详细设计 §3 的 9 张表 + P5 T2 改造新增 2 张表（共 11 张）。

JSON 字段使用 SQLAlchemy 通用 ``JSON`` 类型（SQLite 下以 JSON1 文本存储），
保证迁移 PostgreSQL 时模型无需改动。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from .database import Base


def _now() -> datetime:
    return datetime.now()


class Platform(Base):
    """平台规则表（详细设计 3.1）。"""

    __tablename__ = "platform"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    channel_type: Mapped[str] = mapped_column(String(16), default="web")  # web/api
    url_template: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, default=0)
    page_step: Mapped[int] = mapped_column(Integer, default=0)  # 0=不支持翻页
    selectors: Mapped[dict] = mapped_column(JSON, default=dict)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    cookie: Mapped[str] = mapped_column(Text, default="")
    risk_control_hints: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class Task(Base):
    """任务表（详细设计 3.2）。"""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    template_type: Mapped[str] = mapped_column(String(8), index=True)  # T1~T5
    unit_name: Mapped[str] = mapped_column(String(255), default="")
    keywords: Mapped[str] = mapped_column(Text, default="")
    domain_scope: Mapped[str] = mapped_column(Text, default="")
    platform_ids: Mapped[list] = mapped_column(JSON, default=list)
    max_pages: Mapped[int] = mapped_column(Integer, default=1)
    request_interval: Mapped[float] = mapped_column(Float, default=5.0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending/running/paused_manual/done/failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    units: Mapped[list["TaskUnit"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskUnit(Base):
    """组合状态表：关键词×平台×页码（详细设计 3.3，断点续跑核心）。"""

    __tablename__ = "task_unit"
    __table_args__ = (
        UniqueConstraint("task_id", "platform_id", "keyword", "page", name="uq_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platform.id"), index=True)
    keyword: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer, default=1)
    # pending/running/done/blocked/failed
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str] = mapped_column(Text, default="")
    searched_at: Mapped[datetime | None] = mapped_column(nullable=True)

    task: Mapped[Task] = relationship(back_populates="units")


class SearchResult(Base):
    """检索结果表（详细设计 3.4）。"""

    __tablename__ = "search_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_unit.id"), nullable=True, index=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platform.id"), index=True)
    keyword: Mapped[str] = mapped_column(Text, index=True)
    page: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, index=True)
    is_external: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str] = mapped_column(Text, default="")
    searched_at: Mapped[datetime] = mapped_column(default=_now, index=True)


class SensitiveRule(Base):
    """敏感规则表（详细设计 3.5）。"""

    __tablename__ = "sensitive_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(8), index=True)  # high/medium/low
    pattern: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class SensitiveHit(Base):
    """敏感命中表（详细设计 3.6）。"""

    __tablename__ = "sensitive_hit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("sensitive_rule.id"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(8), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    source_type: Mapped[str] = mapped_column(String(16), default="page")  # page/attachment
    source_url: Mapped[str] = mapped_column(Text, default="")
    matched_text: Mapped[str] = mapped_column(Text, default="")  # 脱敏后
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_result.id"), nullable=True, index=True
    )
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachment.id"), nullable=True, index=True
    )
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)


class Attachment(Base):
    """附件表（详细设计 3.7，T3）。"""

    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    result_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_result.id"), nullable=True
    )
    url: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(512), default="")
    file_type: Mapped[str] = mapped_column(String(16), default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    # pending/parsed/failed/skipped
    parse_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    downloaded_at: Mapped[datetime] = mapped_column(default=_now)


class DomainList(Base):
    """域名清单表（详细设计 3.8，T2 产出；P5 扩列支持两阶段归集）。"""

    __tablename__ = "domain_list"
    __table_args__ = (
        UniqueConstraint("task_id", "domain", name="uq_task_domain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    unit_name: Mapped[str] = mapped_column(String(255), default="")
    domain: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(Text, default="")
    # candidate/confirmed/rejected
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    # ---- P5 T2 改造新增 ----
    layer: Mapped[str] = mapped_column(String(8), default="apex", index=True)  # apex/sub
    parent_domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="", index=True)
    confidence: Mapped[str] = mapped_column(String(8), default="low", index=True)
    resolved_ip: Mapped[str] = mapped_column(String(255), default="")
    alive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    evidences: Mapped[list["DomainEvidence"]] = relationship(
        back_populates="domain_row", cascade="all, delete-orphan"
    )


class DomainEvidence(Base):
    """域名归属证据表（P5 D6）：一个域名多条证据，驳回/确认不删除。"""

    __tablename__ = "domain_evidence"
    __table_args__ = (
        UniqueConstraint(
            "domain_list_id", "provider", "ref_url", name="uq_evidence"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    domain_list_id: Mapped[int] = mapped_column(
        ForeignKey("domain_list.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(8), default="apex")  # apex/sub
    icp_no: Mapped[str] = mapped_column(String(128), default="")
    icp_unit: Mapped[str] = mapped_column(String(255), default="")
    site_name: Mapped[str] = mapped_column(String(255), default="")
    cert_org: Mapped[str] = mapped_column(String(255), default="")
    ref_url: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    domain_row: Mapped[DomainList] = relationship(back_populates="evidences")


class T2ProviderRun(Base):
    """T2 provider 运行状态表（P5 D5，断点续跑）。"""

    __tablename__ = "t2_provider_run"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "stage", "provider", "target", name="uq_provider_run"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), index=True)
    stage: Mapped[str] = mapped_column(String(8), index=True)  # apex/sub
    provider: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(255), default="")  # 阶段B主域
    # pending/running/done/failed/skipped
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error_msg: Mapped[str] = mapped_column(Text, default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class SyntaxDict(Base):
    """语法包装字典表（详细设计 3.9）。"""

    __tablename__ = "syntax_dict"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    template_type: Mapped[str] = mapped_column(String(8), index=True)  # T2~T5
    expression: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- platform
class PlatformBase(BaseModel):
    code: str = Field(max_length=64)
    name: str
    channel_type: str = "web"
    url_template: str
    page_start: int = 0
    page_step: int = 0
    selectors: dict = {}
    headers: dict = {}
    cookie: str = ""
    risk_control_hints: dict = {}
    enabled: bool = True
    notes: str = ""


class PlatformCreate(PlatformBase):
    pass


class PlatformUpdate(BaseModel):
    name: str | None = None
    channel_type: str | None = None
    url_template: str | None = None
    page_start: int | None = None
    page_step: int | None = None
    selectors: dict | None = None
    headers: dict | None = None
    cookie: str | None = None
    risk_control_hints: dict | None = None
    enabled: bool | None = None
    notes: str | None = None


class PlatformOut(ORMModel):
    id: int
    code: str
    name: str
    channel_type: str
    url_template: str
    page_start: int
    page_step: int
    selectors: dict
    headers: dict
    cookie: str
    risk_control_hints: dict
    enabled: bool
    notes: str
    updated_at: datetime


class PlatformTestIn(BaseModel):
    keyword: str = "测试"
    save_screenshot: bool = True


# ---------------------------------------------------------------- task
class TaskCreate(BaseModel):
    name: str
    template_type: str = Field(pattern=r"^T[1-5]$")
    unit_name: str = ""
    keywords: str = ""
    domain_scope: str = ""
    platform_ids: list[int] = []
    max_pages: int = 1
    request_interval: float = 5.0
    params: dict = {}


class TaskUpdate(BaseModel):
    name: str | None = None
    unit_name: str | None = None
    keywords: str | None = None
    domain_scope: str | None = None
    platform_ids: list[int] | None = None
    max_pages: int | None = None
    request_interval: float | None = None
    params: dict | None = None


class TaskOut(ORMModel):
    id: int
    name: str
    template_type: str
    unit_name: str
    keywords: str
    domain_scope: str
    platform_ids: list
    max_pages: int
    request_interval: float
    params: dict
    status: str
    stats: dict
    error_msg: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class UnitOut(ORMModel):
    id: int
    task_id: int
    platform_id: int
    keyword: str
    page: int
    status: str
    attempts: int
    error_msg: str
    screenshot_path: str
    searched_at: Optional[datetime]


# ---------------------------------------------------------------- result
class ResultOut(ORMModel):
    id: int
    task_id: int
    platform_id: int
    keyword: str
    page: int
    title: str
    url: str
    is_external: Optional[bool]
    content_text: str
    screenshot_path: str
    searched_at: datetime
    platform_name: str = ""


class HitOut(ORMModel):
    id: int
    rule_id: Optional[int]
    level: str
    category: str
    source_type: str
    source_url: str
    matched_text: str
    result_id: Optional[int]
    attachment_id: Optional[int]
    task_id: int
    created_at: datetime


# ---------------------------------------------------------------- rule
class RuleBase(BaseModel):
    name: str
    category: str
    level: str = Field(pattern=r"^(high|medium|low)$")
    pattern: str
    enabled: bool = True
    description: str = ""


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    level: str | None = None
    pattern: str | None = None
    enabled: bool | None = None
    description: str | None = None


class RuleOut(ORMModel):
    id: int
    name: str
    category: str
    level: str
    pattern: str
    enabled: bool
    description: str
    updated_at: datetime


# ---------------------------------------------------------------- syntax
class SyntaxBase(BaseModel):
    name: str
    template_type: str = Field(pattern=r"^T[2-5]$")
    expression: str
    enabled: bool = True


class SyntaxCreate(SyntaxBase):
    pass


class SyntaxUpdate(BaseModel):
    name: str | None = None
    template_type: str | None = None
    expression: str | None = None
    enabled: bool | None = None


class SyntaxOut(ORMModel):
    id: int
    name: str
    template_type: str
    expression: str
    enabled: bool
    updated_at: datetime


# ---------------------------------------------------------------- others
class AttachmentOut(ORMModel):
    id: int
    task_id: int
    result_id: Optional[int]
    url: str
    filename: str
    file_type: str
    file_path: str
    size: int
    parse_status: str
    error_msg: str
    downloaded_at: datetime


class DomainOut(ORMModel):
    id: int
    task_id: int
    unit_name: str
    domain: str
    source: str
    status: str


class DomainPatch(BaseModel):
    status: str = Field(pattern=r"^(candidate|confirmed|rejected)$")


class ListResponse(BaseModel):
    total: int
    items: list[Any]


class MessageOut(BaseModel):
    message: str

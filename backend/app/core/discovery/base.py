"""T2 discovery 子系统：统一数据结构、Provider 协议与异常。

Provider 只产出结果、不写库；由 pipeline 统一归并落库（见 merge.py）。
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ...models import Task

# provider 优先级：越小越权威（domain_list.provider 取最高优先级来源）
PROVIDER_PRIORITY = {
    "miit": 0,
    "chinaz": 1,
    "fofa": 10,
    "hunter": 11,
    "quake": 12,
    "crtsh": 20,
    "otx": 21,
    "hackertarget": 22,
    "rapiddns": 23,
    "jldc": 24,
    "subfinder": 25,
    "se_general": 40,
    "brute": 50,
    "manual": 60,
}

PROVIDER_LABELS = {
    "miit": "工信部ICP备案",
    "chinaz": "站长备案API",
    "fofa": "FOFA",
    "hunter": "Hunter鹰图",
    "quake": "Quake360",
    "se_general": "通用搜索引擎",
    "crtsh": "crt.sh证书日志",
    "otx": "AlienVault OTX",
    "hackertarget": "HackerTarget",
    "rapiddns": "RapidDNS",
    "jldc": "jldc(Anubis)",
    "subfinder": "subfinder",
    "brute": "DNS字典爆破",
    "manual": "手工录入",
}

STAGE_APEX = "apex"
STAGE_SUB = "sub"


class ProviderError(Exception):
    """provider 可恢复/不可恢复错误的基类。"""


class ProviderSkipped(ProviderError):
    """未配置/禁用/额度耗尽：记 skipped 而非 failed。"""


@dataclass
class Evidence:
    """一条域名归属证据。"""

    provider: str
    stage: str = STAGE_APEX
    icp_no: str = ""
    icp_unit: str = ""
    site_name: str = ""
    cert_org: str = ""
    ref_url: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class ApexResult:
    """阶段 A 产出：一个候选主域 + 一条证据。"""

    domain: str
    evidence: Evidence


@dataclass
class SubResult:
    """阶段 B 产出：一个子域 + 可选证据。"""

    host: str
    apex: str
    evidence: Evidence | None = None


@dataclass
class ProviderContext:
    """单次 provider 执行的运行时上下文。"""

    task: Task
    settings: dict
    stage: str
    emit: Callable[[dict], Awaitable[None]]
    cancelled: Callable[[], bool]  # 返回任务是否已取消
    target: str = ""           # 阶段 B 的主域
    aliases: list[str] = field(default_factory=list)
    http_timeout: float = 15.0
    max_pages: int = 2
    page_size: int = 100
    se_platform_ids: list[int] = field(default_factory=list)
    se_max_pages: int = 1

    @property
    def unit_name(self) -> str:
        return (self.task.unit_name or "").strip()

    async def log(self, message: str) -> None:
        await self.emit({"type": "log", "message": message})


@runtime_checkable
class ApexProvider(Protocol):
    code: str
    display_name: str

    def is_configured(self, settings: dict) -> bool: ...

    def run(self, ctx: ProviderContext) -> AsyncIterator[ApexResult]: ...


@runtime_checkable
class SubProvider(Protocol):
    code: str
    display_name: str

    def is_configured(self, settings: dict) -> bool: ...

    def run(self, ctx: ProviderContext, apex: str) -> AsyncIterator[SubResult]: ...

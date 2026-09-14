"""采集通道的统一数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FetchedPage:
    """一次抓取的标准化结果，api/web 双通道共用。"""

    url: str
    status: int = 0
    html: str = ""
    text: str = ""
    title: str = ""
    json_data: object = None
    screenshot_path: str = ""
    cookies: list[dict] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    error: str = ""

"""全局配置与运行时路径。

所有运行时产物（SQLite、截图、附件、设置文件）统一落在仓库根的 ``data/`` 目录，
为日后迁移到 PostgreSQL / 独立存储预留路径常量。
"""
from __future__ import annotations

import json
from pathlib import Path

# backend/app/config.py -> parents[0]=app [1]=backend [2]=项目根
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
ATTACHMENT_DIR = DATA_DIR / "attachments"
DB_PATH = DATA_DIR / "sdscan.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

HOST = "127.0.0.1"
PORT = 8000

DEFAULT_SETTINGS = {
    "default_request_interval": 5.0,   # 默认请求间隔（秒）
    "default_max_pages": 1,            # 新建任务默认翻页数
    "http_timeout": 20.0,              # httpx 超时（秒）
    "page_wait_ms": 800,               # Playwright 页面渲染额外等待（毫秒）
    "github_token": "",                # GitHub API token（写入 platform headers）
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "t5_max_detail": 10,               # T5 每个结果页最多跟进正文页数量
    "t3_download_limit": 20,           # T3 每个任务最多下载附件数量
}


def ensure_dirs() -> None:
    """启动时确保运行时目录存在。"""
    for d in (DATA_DIR, SCREENSHOT_DIR, ATTACHMENT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **data}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    ensure_dirs()
    merged = {**DEFAULT_SETTINGS, **data}
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged

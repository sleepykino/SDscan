"""全局配置与运行时路径。

所有运行时产物（SQLite、截图、附件、设置文件）统一落在仓库根的 ``data/`` 目录，
为日后迁移到 PostgreSQL / 独立存储预留路径常量。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# backend/app/config.py -> parents[0]=app [1]=backend [2]=项目根
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
ATTACHMENT_DIR = DATA_DIR / "attachments"
TOOL_DIR = DATA_DIR / "tools"  # 外部工具（subfinder.exe 等，由使用者自行放置）
WORDLIST_DIR = DATA_DIR / "wordlists"
DB_PATH = DATA_DIR / "sdscan.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

HOST = os.environ.get("SDSCAN_HOST", "127.0.0.1")
PORT = int(os.environ.get("SDSCAN_PORT", "8000"))

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
    # ---- P5 T2 域名归集 ----
    "t2_apex_enabled": {               # 阶段A 数据源总开关
        "miit": True, "chinaz": True, "fofa": True, "hunter": True,
        "quake": True, "se_general": True,
    },
    "t2_sub_enabled": {                # 阶段B 子域源总开关（爆破默认关）
        "crtsh": True, "otx": True, "hackertarget": True, "rapiddns": True,
        "jldc": True, "fofa": True, "hunter": True, "quake": True,
        "subfinder": True, "brute": False,
    },
    "fofa_email": "",
    "fofa_key": "",
    "hunter_key": "",
    "quake_key": "",
    "chinaz_key": "",
    "miit_cookie": "",                 # 工信部过码后自动回填
    "subfinder_bin_path": "",          # 空则 subfinder 源 skipped
    "t2_passive_timeout": 15,          # 被动 HTTP 源超时（秒）
    "t2_engine_max_pages": 2,          # 测绘引擎默认分页数
    "t2_brute_dict_path": "",          # 空则用 discovery 内置字典
    "t2_brute_concurrency": 50,
    "t2_dns_timeout": 5,
}

# 敏感设置项：GET /settings 时掩码，PUT 收到掩码值时忽略
SECRET_SETTINGS_KEYS = ("github_token", "fofa_key", "hunter_key", "quake_key",
                        "chinaz_key", "miit_cookie")


def ensure_dirs() -> None:
    """启动时确保运行时目录存在。"""
    for d in (DATA_DIR, SCREENSHOT_DIR, ATTACHMENT_DIR, TOOL_DIR, WORDLIST_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **data}
            # 开关组做一层深合并，缺省 provider 自动补默认值
            for key in ("t2_apex_enabled", "t2_sub_enabled"):
                merged[key] = {**DEFAULT_SETTINGS[key], **(data.get(key) or {})}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> dict:
    ensure_dirs()
    merged = {**DEFAULT_SETTINGS, **data}
    for key in ("t2_apex_enabled", "t2_sub_enabled"):
        if key in data:
            merged[key] = {**DEFAULT_SETTINGS[key], **(data.get(key) or {})}
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged

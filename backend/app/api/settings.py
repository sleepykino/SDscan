"""全局设置：默认间隔、超时、GitHub token 等。"""
from __future__ import annotations

from fastapi import APIRouter

from ..config import load_settings, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    # 读取时回显占位，避免 token 明文暴露在网络响应中
    settings = load_settings()
    if settings.get("github_token"):
        settings = {**settings, "github_token": "********"}
    return settings


@router.put("")
def put_settings(payload: dict):
    current = load_settings()
    allowed = {
        "default_request_interval",
        "default_max_pages",
        "http_timeout",
        "page_wait_ms",
        "github_token",
        "user_agent",
        "t5_max_detail",
        "t3_download_limit",
    }
    update = {k: v for k, v in payload.items() if k in allowed}
    if update.get("github_token") == "********":
        update.pop("github_token")
    merged = save_settings({**current, **update})
    return {**merged, "github_token": "********" if merged.get("github_token") else ""}

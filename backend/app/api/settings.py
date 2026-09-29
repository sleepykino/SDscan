"""全局设置：默认间隔、超时、各数据源 Key、T2 开关等。"""
from __future__ import annotations

from fastapi import APIRouter

from ..config import SECRET_SETTINGS_KEYS, load_settings, save_settings
from .. import schemas

router = APIRouter(prefix="/settings", tags=["settings"])

_ALLOWED = {
    "default_request_interval",
    "default_max_pages",
    "http_timeout",
    "page_wait_ms",
    "github_token",
    "user_agent",
    "t5_max_detail",
    "t3_download_limit",
    # P5 T2
    "t2_apex_enabled",
    "t2_sub_enabled",
    "fofa_email",
    "fofa_key",
    "hunter_key",
    "quake_key",
    "chinaz_key",
    "miit_cookie",
    "subfinder_bin_path",
    "t2_passive_timeout",
    "t2_engine_max_pages",
    "t2_brute_dict_path",
    "t2_brute_concurrency",
    "t2_dns_timeout",
}


def _masked(settings: dict) -> dict:
    out = dict(settings)
    for key in SECRET_SETTINGS_KEYS:
        if out.get(key):
            out[key] = "********"
    return out


@router.get("")
def get_settings():
    return _masked(load_settings())


@router.put("")
def put_settings(payload: dict):
    current = load_settings()
    update = {k: v for k, v in payload.items() if k in _ALLOWED}
    # 掩码回显值视为“不修改”
    for key in SECRET_SETTINGS_KEYS:
        if update.get(key) == "********":
            update.pop(key, None)
    merged = save_settings({**current, **update})
    return _masked(merged)


@router.post("/test-provider")
async def test_provider(payload: schemas.TestProviderIn):
    """测试 T2 数据源连通性：引擎做最小查询，subfinder 检查 exe。"""
    from ..core.discovery import registry
    from ..core.discovery.engines import (
        fofa_search,
        hunter_search,
        quake_search,
        subdomain_query,
    )

    settings = load_settings()
    code = payload.provider
    try:
        if code in ("fofa", "hunter", "quake"):
            search = {"fofa": fofa_search, "hunter": hunter_search,
                      "quake": quake_search}[code]
            assets = await search(
                settings, subdomain_query(code, "example.com"),
                max_pages=1, page_size=1, timeout=15,
            )
            return {"ok": True, "detail": f"连通正常，返回 {len(assets)} 条样例资产"}
        if code == "chinaz":
            inst = registry.get_provider("chinaz")
            if not inst.is_configured(settings):
                return {"ok": False, "detail": "未配置站长 APIKey"}
            return {"ok": True, "detail": "已配置 APIKey（未消耗额度）"}
        if code == "subfinder":
            inst = registry.get_provider("subfinder")
            if not inst.is_configured(settings):
                return {"ok": False, "detail": "未找到 subfinder exe，请配置路径"}
            ver = await inst.version(settings)
            return {"ok": True, "detail": ver[:120] or "可执行文件就绪"}
        if code in ("miit", "se_general"):
            return {"ok": True, "detail": "该源无需 Key，运行时验证"}
        inst = registry.get_provider(code)
        if not inst.is_configured(settings):
            return {"ok": False, "detail": "该数据源当前未启用或缺少前置条件"}
        return {"ok": True, "detail": "配置就绪"}
    except Exception as exc:  # noqa: BLE001 测试按钮直接回显错误
        return {"ok": False, "detail": str(exc)[:200]}

"""两阶段 provider 注册表与选择逻辑（支持测试期注入打桩 provider）。"""
from __future__ import annotations

from .apex.chinaz import ChinazApex
from .apex.engines import FofaApex, HunterApex, QuakeApex
from .apex.miit import MiitApex
from .apex.se_general import SeGeneralApex
from .subdomain.crtsh import CrtshSub
from .subdomain.engines import FofaSub, HunterSub, QuakeSub
from .subdomain.hackertarget import HackerTargetSub
from .subdomain.jldc import JldcSub
from .subdomain.otx import OtxSub
from .subdomain.rapiddns import RapidDnsSub
from .subdomain.brute import BruteDns
from .subdomain.subfinder_cli import SubfinderCli

APEX_PROVIDERS = [
    MiitApex, ChinazApex, FofaApex, HunterApex, QuakeApex, SeGeneralApex,
]
SUB_PROVIDERS = [
    CrtshSub, OtxSub, HackerTargetSub, RapidDnsSub, JldcSub,
    FofaSub, HunterSub, QuakeSub, SubfinderCli, BruteDns,
]

# 测试注入：{code: provider 实例}
_overrides: dict[str, object] = {}

# 单例（无状态 provider 复用；miit 的等待事件在模块级）
_instances: dict[str, object] = {}


def set_override(code: str, instance: object | None) -> None:
    """测试用：注入打桩 provider；传 None 移除。"""
    if instance is None:
        _overrides.pop(code, None)
    else:
        _overrides[code] = instance


def get_provider(code: str):
    if code in _overrides:
        return _overrides[code]
    if code in _instances:
        return _instances[code]
    for cls in (*APEX_PROVIDERS, *SUB_PROVIDERS):
        if cls.code == code:
            inst = cls()
            _instances[code] = inst
            return inst
    raise KeyError(f"未知 provider：{code}")


def all_codes(stage: str) -> list[str]:
    return [c.code for c in (APEX_PROVIDERS if stage == "apex" else SUB_PROVIDERS)]


def switch_map(settings: dict, stage: str) -> dict:
    return settings.get(
        "t2_apex_enabled" if stage == "apex" else "t2_sub_enabled", {}
    ) or {}


def selected_codes(stage: str, task_params: dict, settings: dict) -> list[str]:
    """任务勾选 → 注册表顺序；空列表 = 设置中启用的全部。

    显式勾选的测试打桩 provider（在 _overrides 中）即使不在内置注册表里也保留，
    顺序遵循任务勾选顺序。
    """
    key = "apex_providers" if stage == "apex" else "sub_providers"
    chosen = list(task_params.get(key) or [])
    codes = all_codes(stage)
    if chosen:
        chosen_set = set(chosen)
        registered = [c for c in codes if c in chosen_set]
        extras = [c for c in chosen if c in _overrides and c not in registered]
        return registered + extras
    return [c for c in codes if switch_map(settings, stage).get(c, True)]

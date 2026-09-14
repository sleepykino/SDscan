"""敏感规则匹配与命中文本脱敏。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import SensitiveRule

# 各类命中文本的「保留前 N / 保留后 M」字符
MASK_RULES = {
    "证件号码": (3, 4),
    "联系方式": (3, 4),
    "员工隐私": (2, 2),
}
DEFAULT_MASK = (2, 2)
MAX_MATCH_LEN = 200


@dataclass
class Match:
    rule: SensitiveRule
    raw: str  # 脱敏前文本（仅用于匹配过程，不落库）


def mask_text(text: str, category: str) -> str:
    """按分类脱敏；过短无法保留前后缀时整体打码。"""
    text = text.strip()
    if len(text) > MAX_MATCH_LEN:
        text = text[:MAX_MATCH_LEN]
    head, tail = MASK_RULES.get(category, DEFAULT_MASK)
    if len(text) <= head + tail:
        return "*" * len(text)
    middle = "*" * min(len(text) - head - tail, 12)
    return f"{text[:head]}{middle}{text[-tail:]}"


class SensitiveMatcher:
    """加载启用规则并对文本做批量匹配。"""

    def __init__(self, rules: list[SensitiveRule]) -> None:
        self._compiled: list[tuple[SensitiveRule, re.Pattern]] = []
        for rule in rules:
            if not rule.enabled:
                continue
            try:
                self._compiled.append((rule, re.compile(rule.pattern)))
            except re.error:
                # 非法正则不影响其它规则
                continue

    def find(self, text: str) -> list[tuple[SensitiveRule, str]]:
        """返回 (规则, 命中原文) 列表，同一规则去重命中串。"""
        if not text or not self._compiled:
            return []
        hits: list[tuple[SensitiveRule, str]] = []
        for rule, pattern in self._compiled:
            seen: set[str] = set()
            for match in pattern.finditer(text):
                raw = self._best_group(match)
                if not raw or raw in seen:
                    continue
                seen.add(raw)
                hits.append((rule, raw))
        return hits

    @staticmethod
    def _best_group(match: re.Match) -> str:
        """带前后边界环视的正则取最有信息量的捕获组，否则取整体匹配。"""
        groups = [g for g in match.groups() if g]
        if groups:
            return max(groups, key=len).strip()
        return match.group(0).strip()

    @staticmethod
    def desensitize(rule: SensitiveRule, raw: str) -> str:
        return mask_text(raw, rule.category)

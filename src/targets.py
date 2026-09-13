"""按 id 或关键词定位唯一目标事件（修改 / 删除的第一步）。

与 src/event_match.py 一样保持确定性：这里不做自然语言解析，
Codex 负责把「明天下午和壁仞的会议」换算成 --date / --from+--to 与 --query。

安全底线（简化流程但不下调）：
- 0 个命中：明确报「没找到」，绝不构造 event id，也不创建新事件顶替
- ≥2 个命中：列出候选让用户选，禁止猜测
- 恰好 1 个命中：视为已授权，直接交给调用方执行
"""

from __future__ import annotations

from datetime import datetime

from src.datetime_utils import day_bounds, parse_iso
from src.event_match import match_events

# 需要人工决策（没找到 / 多候选 / 影响范围待确认）时的退出码
EXIT_NEEDS_CHOICE = 4


def resolve_range(date_value: str | None, start_iso: str | None,
                  end_iso: str | None) -> tuple[datetime, datetime]:
    """把 --date / --from+--to 解析成定位用的时间范围（缺省当天）。"""
    if bool(start_iso) != bool(end_iso):
        raise ValueError("--from 和 --to 必须成对使用（宁大勿小，如「明天下午」= 12:00-18:00）")
    if date_value and (start_iso or end_iso):
        raise ValueError("--date 与 --from/--to 不要同时使用")
    if start_iso and end_iso:
        return parse_iso(start_iso), parse_iso(end_iso)
    return day_bounds(date_value)


def locate_event(service, query: str, start: datetime,
                 end: datetime) -> tuple[dict | None, list[dict]]:
    """在 [start, end) 内按关键词定位事件，返回 (target, candidates)。

    恰好 1 个命中 → (该事件, [该事件])；0 个或多命中 → (None, 命中列表)，
    由脚本负责汇报并停下，让用户澄清。
    """
    candidates = match_events(service.list_events(start, end), query)
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates

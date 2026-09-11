"""时间冲突检测（与日历后端无关的纯算法）。

用于创建 / 移动日程前的冲突检查：给定候选忙碌事件与目标时间范围，
返回所有与其重叠的事件。与 free_time 一致，所有事件一律视为忙碌。
"""

from __future__ import annotations

from datetime import datetime


def find_conflicts(
    events: list[dict],
    start: datetime,
    end: datetime,
    exclude_event_id: str | None = None,
) -> list[dict]:
    """返回与 [start, end) 重叠的事件（保持原顺序）。

    - exclude_event_id：移动已有事件时排除其自身，避免把自己判为冲突
    - 重叠定义：事件与目标区间有严格的时间交集（首尾相接不算冲突）
    - start/end 缺失或零时长的事件被忽略（与 find_free_slots 一致）
    - 全天事件按 00:00 ~ 次日 00:00 参与，自然与当天任何日程冲突
    """
    if end <= start:
        raise ValueError(f"时间范围无效（结束必须晚于开始）: {start} -> {end}")

    conflicts: list[dict] = []
    for event in events:
        if exclude_event_id and event.get("id") == exclude_event_id:
            continue
        ev_start, ev_end = event.get("start"), event.get("end")
        if ev_start is None or ev_end is None or ev_start >= ev_end:
            continue
        if ev_start < end and start < ev_end:
            conflicts.append(event)
    return conflicts

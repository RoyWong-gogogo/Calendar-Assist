"""空闲时间计算（与日历后端无关的纯算法）。

v0.1 的简化假设：日历上的所有事件都视为忙碌（不区分 Graph 的 showAs
空闲状态或 ICS 的 TRANSP 属性）。后续有需要再细化。
"""

from __future__ import annotations

from datetime import datetime, timedelta


def find_free_slots(
    busy_events: list[dict],
    window_start: datetime,
    window_end: datetime,
    duration: timedelta,
) -> list[tuple[datetime, datetime]]:
    """在 [window_start, window_end) 内返回所有 ≥ duration 的最大空闲区间。

    busy_events 为 list_events 的返回值（各后端结构一致）：
    - 事件的 start/end 为 timezone-aware datetime（None 的忽略）
    - 超出窗口的部分被裁剪；重叠/相邻的忙碌区间会被合并
    - 返回值按时间升序，每个区间都是可容纳 duration 的最大连续空闲段
    """
    if duration <= timedelta(0):
        raise ValueError(f"时长必须为正: {duration}")
    if window_end <= window_start:
        raise ValueError(
            f"时间范围无效（结束必须晚于开始）: {window_start} -> {window_end}"
        )

    # 收集并裁剪到窗口内的忙碌区间
    clipped: list[tuple[datetime, datetime]] = []
    for event in busy_events:
        start, end = event.get("start"), event.get("end")
        if start is None or end is None:
            continue
        start = max(start, window_start)
        end = min(end, window_end)
        if start < end:
            clipped.append((start, end))

    # 合并重叠或相邻的忙碌区间
    clipped.sort()
    merged: list[list[datetime]] = []
    for start, end in clipped:
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])

    # 空闲区间 = 合并后忙碌区间之间的空隙（≥ duration 才返回）
    free: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for start, end in merged:
        if start - cursor >= duration:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if window_end - cursor >= duration:
        free.append((cursor, window_end))
    return free

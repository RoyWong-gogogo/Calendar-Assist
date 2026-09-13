"""写操作后的终端汇报（事后提醒，不阻塞、不改变退出码）。

设计原则：创建 / 修改日程不做事前冲突预检与会议室忙闲预检（延迟高、交互轮次多），
改为写入后读一次目标时段，把重叠的已有日程报出来；会议室是否真的订上，
则看事件里 resource 与会人的响应状态（跨邮箱忙闲缓存有延迟，忙闲视图不可靠）。
"""

from __future__ import annotations

from datetime import datetime

from src.attendees import describe, is_resource
from src.conflicts import find_conflicts
from src.datetime_utils import get_tz
from src.rooms import room_label


def format_range(start: datetime | None, end: datetime | None, tz=None,
                 all_day: bool = False) -> str:
    """人类可读的时间范围（同一天省略日期）。"""
    if start is None or end is None:
        return "时间未知"
    tz = tz or get_tz()
    start, end = start.astimezone(tz), end.astimezone(tz)
    if all_day:
        return f"{start:%Y-%m-%d} 全天"
    if start.date() == end.date():
        return f"{start:%Y-%m-%d %H:%M}~{end:%H:%M}"
    return f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"


def event_line(ev: dict, tz=None) -> str:
    """一行摘要：[时间] 标题。"""
    return f"[{format_range(ev.get('start'), ev.get('end'), tz, bool(ev.get('all_day')))}] {ev.get('title')}"


def print_event_detail(ev: dict, indent: str = "    ") -> None:
    """打印日程的地点 / 会议室 / 备注（时间与标题由调用方负责）。"""
    if ev.get("location"):
        print(f"{indent}地点: {ev['location']}")
    rooms = ev.get("rooms")
    if rooms:
        print(f"{indent}会议室: {', '.join(rooms)}")
    description = (ev.get("description") or "").strip()
    if description:
        print(f"{indent}备注: {description[:80]}" + ("…" if len(description) > 80 else ""))


def print_attendees(ev: dict, indent: str = "    ", label: str = "与会人") -> None:
    """打印普通与会人（会议室由「会议室」那一行负责，这里不重复）。"""
    people = [entry for entry in (ev.get("attendees") or []) if not is_resource(entry)]
    if not people:
        return
    print(f"{indent}{label}: " + "，".join(describe(entry) for entry in people))


def print_candidates(candidates: list[dict], tz=None) -> None:
    """列出多个候选（含 event id），让用户挑选；脚本禁止猜。"""
    tz = tz or get_tz()
    print(f"⚠️ 匹配到 {len(candidates)} 个日程，请确认是哪一个（再用 --event-id 指定）:")
    for index, ev in enumerate(candidates, 1):
        print(f"{index}. {event_line(ev, tz)}")
        print_event_detail(ev, indent="   ")
        print(f"   event id: {ev['id']}")


def print_no_match(query: str, start: datetime, end: datetime) -> None:
    """0 命中时的标准汇报（不构造 event id）。"""
    print(f"没有找到匹配「{query}」的日程（搜索范围 {format_range(start, end)}）。")
    print("请确认关键词或扩大范围（--date / --from --to，宁大勿小）；不要把不存在的日程当成已找到。")


def print_conflict_notice(service, start: datetime, end: datetime,
                          exclude_event_id: str | None = None,
                          label: str = "事后提醒") -> list[dict]:
    """读一次目标时段并打印重叠的其它日程；没有则打印一行确认。

    提醒失败不会改变调用方的退出码（写操作已经成功了），只打印提示。
    """
    try:
        events = service.list_events(start, end)
    except RuntimeError as exc:
        print(f"[{label}] 读取目标时段失败，未能核对：{exc}")
        return []
    conflicts = find_conflicts(events, start, end, exclude_event_id=exclude_event_id)
    if not conflicts:
        print(f"[{label}] 该时段没有其它日程")
        return []
    tz = get_tz()
    print(f"⚠️ [{label}] 该时段还有 {len(conflicts)} 个日程:")
    for ev in conflicts:
        print(f"  - {event_line(ev, tz)}")
    return conflicts


def room_response(ev: dict, address: str) -> str | None:
    """从事件字典的 room_responses 里取指定会议室的响应状态。"""
    wanted = (address or "").lower()
    for entry in ev.get("room_responses") or []:
        if (entry.get("address") or "").lower() == wanted:
            return entry.get("response")
    return None


def print_room_notice(ev: dict, address: str) -> str | None:
    """打印会议室邀请的响应状态（accepted = 已订上），返回该状态。"""
    label = room_label(address)
    response = room_response(ev, address)
    if response == "accepted":
        print(f"✅ 会议室 {label}: 已接受邀请")
    elif response == "tentativelyAccepted":
        print(f"✅ 会议室 {label}: 暂定接受（tentativelyAccepted）")
    elif response in (None, "none", "notResponded"):
        print(f"ℹ️ 会议室 {label}: 尚未响应——房间通常几秒内自动接受，"
              "稍后可查事件详情确认；若一直不接受，可能是房间邮箱不存在或该时段不可用")
    elif response == "declined":
        print(f"⚠️ 会议室 {label}: 已拒绝该时段（房间被占用或不可预订），请换一间")
    else:
        print(f"⚠️ 会议室 {label}: 响应状态 {response}，请人工确认")
    return response

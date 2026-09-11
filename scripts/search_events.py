"""按时间范围 + 关键词搜索日程，列出候选事件（只读）。

用于"把明天下午和壁仞的会议改到四点"这类请求的第一步：
先实际读取日历、过滤候选，拿到真实 event id 后再进入修改/删除流程。

用法（项目根目录）：
    python scripts/search_events.py --from 2026-09-13T12:00 --to 2026-09-13T18:00 --query 壁仞
    python scripts/search_events.py --date tomorrow --query 客户
    python scripts/search_events.py --date 2026-09-14                    # 不限关键词，列出全部

匹配规则：标题 / 地点 / 备注 包含全部关键词（大小写不敏感）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datetime_utils import day_bounds, get_tz, parse_iso, to_iso
from src.event_match import match_events
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="搜索日程（只读，返回候选）")
    parser.add_argument("--date", help="today | tomorrow | yesterday | YYYY-MM-DD（与 --from/--to 二选一）")
    parser.add_argument("--from", dest="start", metavar="ISO", help="范围开始（ISO 8601）")
    parser.add_argument("--to", dest="end", metavar="ISO", help="范围结束（ISO 8601）")
    parser.add_argument("--query", help="标题/地点/备注关键词（空白分隔多词，需全部匹配；省略则不过滤）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    args = parser.parse_args()

    if args.date and (args.start or args.end):
        parser.error("--date 与 --from/--to 不要同时使用")
    if bool(args.start) != bool(args.end):
        parser.error("--from 和 --to 必须成对使用")

    try:
        if args.start and args.end:
            start, end = parse_iso(args.start), parse_iso(args.end)
        else:
            start, end = day_bounds(args.date)
        service = get_calendar_service_class()()
        events = service.list_events(start, end)
        matched = match_events(events, args.query)
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([_to_payload(ev) for ev in matched], ensure_ascii=False, indent=2))
        return 0

    tz = get_tz()
    print(f"搜索范围: {to_iso(start)} ~ {to_iso(end)}" + (f" | 关键词: {args.query}" if args.query else ""))
    if not matched:
        print("（没有找到符合条件的日程）")
        return 0
    for i, ev in enumerate(matched, 1):
        line = f"{i}. [{_format_range(ev, tz)}] {ev['title']}"
        if ev.get("series_master_id") or ev.get("is_series_master"):
            line += "（重复日程）"
        print(line)
        if ev["location"]:
            print(f"   地点: {ev['location']}")
        description = (ev["description"] or "").strip()
        if description:
            print(f"   备注: {description[:80]}" + ("…" if len(description) > 80 else ""))
        print(f"   event id: {ev['id']}")
    return 0


def _to_payload(ev: dict) -> dict:
    return {
        "id": ev["id"],
        "title": ev["title"],
        "start": to_iso(ev["start"]) if ev["start"] else None,
        "end": to_iso(ev["end"]) if ev["end"] else None,
        "all_day": ev["all_day"],
        "location": ev["location"],
        "description": ev["description"],
        "series_master_id": ev.get("series_master_id"),
        "is_series_master": ev.get("is_series_master", False),
    }


def _format_range(ev: dict, tz) -> str:
    start, end = ev["start"], ev["end"]
    if start is None or end is None:
        return "时间未知"
    start, end = start.astimezone(tz), end.astimezone(tz)
    if ev["all_day"]:
        return f"{start:%Y-%m-%d} 全天"
    if start.date() == end.date():
        return f"{start:%m-%d %H:%M}~{end:%H:%M}"
    return f"{start:%m-%d %H:%M} ~ {end:%m-%d %H:%M}"


if __name__ == "__main__":
    sys.exit(main())

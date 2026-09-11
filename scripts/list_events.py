"""查询日历日程（Outlook / Google 后端由 CALENDAR_PROVIDER 决定）。

用法（项目根目录）：
    python scripts/list_events.py                      # 今天
    python scripts/list_events.py --date tomorrow      # 明天
    python scripts/list_events.py --date 2026-09-12    # 指定日期
    python scripts/list_events.py --from 2026-09-10T09:00 --to 2026-09-10T18:00
    python scripts/list_events.py --json               # JSON 输出（便于程序读取）

Codex 也可以直接调用 src.service_factory.get_calendar_service_class()。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_PROVIDER
from src.datetime_utils import day_bounds, get_tz, parse_iso, to_iso
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 Google Calendar 日程")
    parser.add_argument("--date", help="today | tomorrow | yesterday | YYYY-MM-DD（默认今天）")
    parser.add_argument("--from", dest="start", metavar="ISO", help="时间段开始（ISO 8601）")
    parser.add_argument("--to", dest="end", metavar="ISO", help="时间段结束（ISO 8601）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    args = parser.parse_args()

    if args.date and (args.start or args.end):
        parser.error("--date 与 --from/--to 不要同时使用")
    if bool(args.start) != bool(args.end):
        parser.error("--from 和 --to 必须成对使用")

    try:
        if args.start and args.end:
            start = parse_iso(args.start)
            end = parse_iso(args.end)
        else:
            start, end = day_bounds(args.date)

        ServiceClass = get_calendar_service_class()
        service = ServiceClass()
        events = service.list_events(start, end)
    except RuntimeError as exc:
        # AuthError / CalendarApiError / OutlookApiError 均为 RuntimeError 子类
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = [
            {
                "id": ev["id"],
                "title": ev["title"],
                "start": to_iso(ev["start"]) if ev["start"] else None,
                "end": to_iso(ev["end"]) if ev["end"] else None,
                "all_day": ev["all_day"],
                "location": ev["location"],
                "description": ev["description"],
                "rooms": ev.get("rooms") or [],
            }
            for ev in events
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    tz = get_tz()
    print(f"日历: {service.calendar_id}（{CALENDAR_PROVIDER}） | 时区: {tz.key}")
    print(f"范围: {to_iso(start)} ~ {to_iso(end)}")
    if not events:
        print("（该时间段内没有日程）")
        return 0

    for ev in events:
        print(f"- [{_format_time_range(ev, tz)}] {ev['title']}")
        if ev["location"]:
            print(f"    地点: {ev['location']}")
        if ev.get("rooms"):
            print(f"    会议室: {', '.join(ev['rooms'])}")
        description = (ev["description"] or "").strip()
        if description:
            print(f"    备注: {description}")
    return 0


def _format_time_range(ev: dict, tz) -> str:
    start, end = ev["start"], ev["end"]
    if start is None or end is None:
        return "时间未知"
    start = start.astimezone(tz)
    end = end.astimezone(tz)
    if ev["all_day"]:
        last_day = end.date() - timedelta(days=1)
        if last_day == start.date():
            return f"{start:%Y-%m-%d} 全天"
        return f"{start:%Y-%m-%d} ~ {last_day:%Y-%m-%d} 全天"
    if start.date() == end.date():
        return f"{start:%Y-%m-%d %H:%M}~{end:%H:%M}"
    return f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"


if __name__ == "__main__":
    sys.exit(main())

"""在日历上创建日程（写入操作，当前仅 Outlook 后端支持）。

用法（项目根目录）：
    python scripts/create_event.py --title "和王总开会" --start 2026-09-14T15:00 --end 2026-09-14T16:00
    python scripts/create_event.py --title "周会" --start 2026-09-14T10:00 --duration 60
    python scripts/create_event.py --title "评审" --start 2026-09-15T14:00 --duration 90 --location "会议室 A" --description "评审方案"
    python scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801

Codex 负责把自然语言换算成明确时间后调用本脚本，
也可以直接调用 service_factory 返回的服务类的 create_event。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datetime_utils import get_tz, parse_iso, to_iso
from src.rooms import expand_room
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="创建日历日程")
    parser.add_argument("--title", required=True, help="日程标题")
    parser.add_argument("--start", required=True, metavar="ISO", help="开始时间（ISO 8601）")
    parser.add_argument("--end", metavar="ISO", help="结束时间（ISO 8601；与 --duration 二选一）")
    parser.add_argument("--duration", type=int, metavar="分钟", help="持续时长（分钟；与 --end 二选一）")
    parser.add_argument("--location", help="地点（可选）")
    parser.add_argument("--description", help="备注（可选）")
    parser.add_argument("--room", help="会议室（编号如 801 / 名称 / 完整邮箱），作为 resource 与会人预订")
    parser.add_argument("--force-room", action="store_true",
                        help="会议室已被占用时仍强制创建")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    args = parser.parse_args()

    if bool(args.end) == bool(args.duration):
        parser.error("--end 与 --duration 必须二选一")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration 必须为正整数（分钟）")

    try:
        start = parse_iso(args.start)
        if args.end:
            end = parse_iso(args.end)
        else:
            end = start + timedelta(minutes=args.duration)
        service = get_calendar_service_class()()
        room_address = None
        if args.room:
            if not hasattr(service, "get_schedule"):
                raise RuntimeError(
                    "会议室预订仅 Outlook 后端支持（当前后端没有 get_schedule）"
                )
            room_address = expand_room(args.room)
            info = service.get_schedule([room_address], start, end)[0]
            if info["error"]:
                raise ValueError(
                    f"会议室邮箱不存在或无法解析: {room_address}（{info['error']}）"
                )
            if info["busy"] and not args.force_room:
                tz = get_tz()
                print(f"[会议室占用] {room_address} 在目标时段已被占用:", file=sys.stderr)
                for slot_start, slot_end in info["busy"]:
                    print(
                        f"  - {slot_start.astimezone(tz):%Y-%m-%d %H:%M}"
                        f"~{slot_end.astimezone(tz):%H:%M}",
                        file=sys.stderr,
                    )
                print("请换一间会议室，或加 --force-room 强制创建。", file=sys.stderr)
                return 3
        event = service.create_event(
            title=args.title,
            start=start,
            end=end,
            location=args.location,
            description=args.description,
            room=room_address,
        )
    except RuntimeError as exc:
        # AuthError / OutlookApiError / IcsError 均为 RuntimeError 子类
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "id": event["id"],
            "title": event["title"],
            "start": to_iso(event["start"]) if event["start"] else None,
            "end": to_iso(event["end"]) if event["end"] else None,
            "all_day": event["all_day"],
            "location": event["location"],
            "description": event["description"],
            "rooms": event.get("rooms") or [],
        }, ensure_ascii=False, indent=2))
        return 0

    tz = get_tz()
    print("已创建日程:")
    start_s = event["start"].astimezone(tz)
    end_s = event["end"].astimezone(tz)
    if start_s.date() == end_s.date():
        time_range = f"{start_s:%Y-%m-%d %H:%M}~{end_s:%H:%M}"
    else:
        time_range = f"{start_s:%Y-%m-%d %H:%M} ~ {end_s:%Y-%m-%d %H:%M}"
    print(f"- [{time_range}] {event['title']}")
    if event["location"]:
        print(f"    地点: {event['location']}")
    if event.get("rooms"):
        print(f"    会议室: {', '.join(event['rooms'])}")
    description = (event["description"] or "").strip()
    if description:
        print(f"    备注: {description}")
    print(f"    id: {event['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""在日历上创建日程（写入操作，当前仅 Outlook 后端支持）。

用法（项目根目录）：
    python scripts/create_event.py --title "和王总开会" --start 2026-09-14T15:00 --end 2026-09-14T16:00
    python scripts/create_event.py --title "周会" --start 2026-09-14T10:00 --duration 60
    python scripts/create_event.py --title "评审" --start 2026-09-15T14:00 --duration 90 --location "会议室 A" --description "评审方案"
    python scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801
    python scripts/create_event.py --title "AI 工具使用现状汇报" --start 2026-09-14T14:00 --duration 60 --attendee "Emma Zhou" --attendee nzhou@arraycomm.com

创建成功后会做一次事后提醒（该时段是否已有其它日程、会议室是否接受邀请）；
写操作本身不做事前冲突 / 忙闲预检（延迟高），需要预检时先跑 list_events / list_rooms。

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
from src.attendees import is_resource
from src.notices import print_attendees, print_conflict_notice, print_room_notice
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
    parser.add_argument("--attendee", action="append", metavar="邮箱|姓名",
                        help="与会人（邮箱，或通讯录 data/contacts.csv 里的姓名；可重复传入，required 类型）")
    parser.add_argument("--force-room", action="store_true",
                        help="兼容保留（已不做事前忙闲预检，加不加都会创建）")
    parser.add_argument("--no-notice", action="store_true",
                        help="跳过创建后的事后冲突提醒")
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
        room_address = expand_room(args.room) if args.room else None
        event = service.create_event(
            title=args.title,
            start=start,
            end=end,
            location=args.location,
            description=args.description,
            room=room_address,
            attendees=args.attendee,
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
            "room_responses": event.get("room_responses") or [],
            "attendees": [entry["address"] for entry in (event.get("attendees") or [])
                          if not is_resource(entry)],
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
    if event.get("attendees"):
        print_attendees(event)   # 回读的名字 <邮箱>，比回显输入更可靠
    elif args.attendee:
        print(f"    与会人: {', '.join(args.attendee)}")
    if event.get("rooms"):
        print(f"    会议室: {', '.join(event['rooms'])}")
    description = (event["description"] or "").strip()
    if description:
        print(f"    备注: {description}")
    print(f"    id: {event['id']}")
    if room_address:
        print_room_notice(event, room_address)
    if not args.no_notice:
        print_conflict_notice(service, start, end, exclude_event_id=event["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""修改日程（默认直接执行；--dry-run 才是预览）。

定位目标两种方式：
    --event-id XXX                        直接用 id（来自 search_events 或上次汇报）
    --query 关键词 --date tomorrow        脚本自己搜索定位（唯一命中即执行）

流程（为降低延迟，写操作不再做事前冲突预检与会议室忙闲预检）：
定位目标 → 恰好 1 个命中就直接改 → 汇报结果 + 事后提醒
（新时段是否已有日程、会议室是否接受邀请）。
0 个命中或 ≥2 个候选会停下并要求澄清（退出码 4）；--yes 保留为兼容空参数。

用法（项目根目录）：
    python scripts/update_event.py --event-id XXX --start 2026-09-14T16:00 --duration 60
    python scripts/update_event.py --query 壁仞 --date tomorrow --start 2026-09-14T16:00 --duration 60
    python scripts/update_event.py --event-id XXX --title "新标题" --location "新地点"
    python scripts/update_event.py --event-id XXX --room 801              # 改会议室
    python scripts/update_event.py --event-id XXX --room ""               # 取消会议室
    python scripts/update_event.py --event-id XXX --attendee a@x.com --attendee b@x.com  # 邀请与会人
    python scripts/update_event.py --event-id XXX --attendee "Nanqing Zhou"             # 也可以直接写姓名（通讯录解析）
    python scripts/update_event.py --event-id XXX --remove-attendee a@x.com              # 移除与会人
    python scripts/update_event.py --event-id XXX --start 2026-09-14T16:00 --dry-run   # 只看不改
    python scripts/update_event.py --event-id XXX --start 2026-09-14T16:00 --no-notice # 不要事后提醒
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.attendees import addresses, merge as merge_people, normalize_address, split_people
from src.contacts import resolve_addresses
from src.datetime_utils import get_tz, parse_iso, to_iso
from src.notices import (
    event_line,
    print_attendees,
    print_candidates,
    print_conflict_notice,
    print_event_detail,
    print_no_match,
    print_room_notice,
)
from src.rooms import expand_room
from src.service_factory import get_calendar_service_class
from src.targets import EXIT_NEEDS_CHOICE, locate_event, resolve_range


def main() -> int:
    parser = argparse.ArgumentParser(description="修改日程（默认执行，--dry-run 预览）")
    parser.add_argument("--event-id", help="目标事件的 event id（与 --query 二选一）")
    parser.add_argument("--query", help="关键词定位目标（标题/地点/备注，需唯一命中）")
    parser.add_argument("--date", help="定位搜索范围: today | tomorrow | yesterday | YYYY-MM-DD（默认今天）")
    parser.add_argument("--from", dest="range_from", metavar="ISO",
                        help="定位搜索范围开始（与 --to 成对；宁大勿小）")
    parser.add_argument("--to", dest="range_to", metavar="ISO",
                        help="定位搜索范围结束（与 --from 成对）")
    parser.add_argument("--title", help="新标题（可选）")
    parser.add_argument("--start", metavar="ISO", help="新开始时间（ISO 8601，可选）")
    parser.add_argument("--end", metavar="ISO", help="新结束时间（与 --duration 二选一）")
    parser.add_argument("--duration", type=int, metavar="分钟", help="新持续时长（分钟，与 --end 二选一）")
    parser.add_argument("--location", help="新地点（传空字符串表示清空）")
    parser.add_argument("--room", help="会议室（编号 / 名称 / 邮箱；传空字符串表示取消会议室）")
    parser.add_argument("--attendee", action="append", metavar="邮箱|姓名",
                        help="新增与会人（邮箱，或通讯录 data/contacts.csv 里的姓名；可重复传入，required 类型）")
    parser.add_argument("--remove-attendee", action="append", metavar="邮箱|姓名",
                        help="移除与会人（邮箱或姓名；可重复传入）")
    parser.add_argument("--description", help="新备注（传空字符串表示清空）")
    parser.add_argument("--dry-run", action="store_true", help="只预览不执行")
    parser.add_argument("--no-notice", action="store_true", help="跳过事后冲突提醒")
    parser.add_argument("--yes", action="store_true", help="兼容保留（现在默认即执行）")
    args = parser.parse_args()

    if bool(args.event_id) == bool(args.query):
        parser.error("--event-id 与 --query 必须二选一")
    if args.end is not None and args.duration is not None:
        parser.error("--end 与 --duration 必须二选一")

    # 与会人：只动普通与会人（会议室继续由 --room 负责），空白项忽略
    add_people = [item.strip() for item in (args.attendee or []) if item.strip()]
    drop_people = [item.strip() for item in (args.remove_attendee or []) if item.strip()]

    if not (args.start or args.end or args.duration or args.title is not None
            or args.location is not None or args.description is not None
            or args.room is not None or add_people or drop_people):
        parser.error("至少提供一项要修改的字段（--start / --title / --room / --attendee ...）")

    try:
        # 姓名先按通讯录解析成邮箱（查不到 / 命中多个都报错，绝不猜地址）
        add_people = resolve_addresses(add_people)
        drop_people = resolve_addresses(drop_people)

        service = get_calendar_service_class()()

        # 1) 定位目标：按 id 直接读；按关键词先搜范围，再确认唯一命中
        if args.event_id:
            current = service.get_event(args.event_id)
        else:
            range_start, range_end = resolve_range(args.date, args.range_from, args.range_to)
            current, candidates = locate_event(service, args.query, range_start, range_end)
            if current is None:
                if not candidates:
                    print_no_match(args.query, range_start, range_end)
                else:
                    print_candidates(candidates)
                return EXIT_NEEDS_CHOICE
            if current.get("is_series_master"):
                print("⚠️ 关键词命中的是重复日程的系列母事件，改动会作用于整个系列。")
                print(f"- {event_line(current, get_tz())}")
                print("请确认影响范围后，用 --event-id 明确指定再改。")
                return EXIT_NEEDS_CHOICE

        # 2) 计算修改后的值（未提供的字段沿用当前值）
        new_start = parse_iso(args.start) if args.start else current["start"]
        if args.end is not None:
            new_end = parse_iso(args.end)
        elif args.duration is not None:
            new_end = new_start + timedelta(minutes=args.duration)
        else:
            new_end = current["end"]
        if new_start is None or new_end is None or new_end <= new_start:
            raise ValueError(
                f"修改后的时间无效: {to_iso(new_start)} -> {to_iso(new_end)}"
            )

        time_changed = (new_start != current["start"]) or (new_end != current["end"])

        # 会议室：None=不变；""=取消；其他=改为该会议室（以 resource 与会人形式预订）
        room_changed = args.room is not None
        new_rooms = list(current.get("rooms") or [])
        room_address = None
        if room_changed:
            if args.room.strip():
                room_address = expand_room(args.room)
                new_rooms = [room_address]
            else:
                new_rooms = []

        # 与会人：在原有普通与会人上增删（会议室条目不动，除非同时改了 --room）
        people, _existing_rooms = split_people(current.get("attendees"))
        new_people = merge_people(people, add=add_people, remove=drop_people)
        invited_keys = addresses(people)
        already_invited = [item for item in add_people
                           if normalize_address(item) in invited_keys]
        not_invited = [item for item in drop_people
                       if normalize_address(item) not in invited_keys]

        # 3) 展示原 → 新（写操作本身不再因冲突 / 占用而阻塞）
        tz = get_tz()
        preview = {
            "title": args.title if args.title is not None else current["title"],
            "start": new_start,
            "end": new_end,
            "all_day": current.get("all_day", False),
            "location": args.location if args.location is not None else current["location"],
            "rooms": new_rooms,
            "description": (args.description if args.description is not None
                            else current["description"]),
            "attendees": new_people,
        }
        print("原日程:")
        print(f"- {event_line(current, tz)}")
        print_event_detail(current)
        print_attendees(current)
        print("修改为:")
        print(f"- {event_line(preview, tz)}")
        print_event_detail(preview)
        print_attendees(preview)
        if already_invited:
            print(f"ℹ️ 已在邀请列表中（不会重复邀请）: {', '.join(already_invited)}")
        if not_invited:
            print(f"ℹ️ 不在邀请列表中（无需移除）: {', '.join(not_invited)}")

        if current.get("is_series_master"):
            print("\n⚠️ 这是重复日程的系列母事件：修改将影响整个系列（所有场次）。")
        elif current.get("series_master_id"):
            print("\n⚠️ 这是重复日程的其中一场：修改仅影响这一场。")

        if args.dry_run:
            if not args.no_notice:
                print()
                print_conflict_notice(service, new_start, new_end,
                                      exclude_event_id=current["id"], label="预览")
            print("\n（--dry-run：未修改。去掉 --dry-run 即执行。）")
            return 0

        # 4) 执行（改会议室时复用已经取到的与会人，省一次读取）
        updated = service.update_event(
            current["id"],
            title=args.title,
            start=new_start if args.start or args.duration or args.end else None,
            end=new_end if args.end is not None or args.duration is not None else None,
            location=args.location,
            description=args.description,
            room=args.room,
            attendees=add_people or None,
            remove_attendees=drop_people or None,
            existing_attendees=(current.get("attendees")
                                if (room_changed or add_people or drop_people) else None),
        )
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    # 5) 汇报结果 + 事后提醒
    print()
    print("✅ 已修改日程:")
    print(f"- {event_line(updated, get_tz())}")
    print_event_detail(updated)
    print_attendees(updated)
    if not_invited:
        print(f"ℹ️ 不在邀请列表中（未改动）: {', '.join(not_invited)}")
    if room_address:
        print_room_notice(updated, room_address)
    if time_changed and not args.no_notice:
        print_conflict_notice(service, new_start, new_end,
                              exclude_event_id=current["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())


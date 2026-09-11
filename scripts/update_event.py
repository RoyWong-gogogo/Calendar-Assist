"""修改日程（安全模式：默认预览原→新，--yes 才真正执行）。

必须通过真实 event id 修改（可先用 scripts/search_events.py 找到候选）。
执行前自动做冲突检查（排除事件自身）。

用法（项目根目录）：
    python scripts/update_event.py --event-id XXX --start 2026-09-14T16:00 --duration 60          # 预览
    python scripts/update_event.py --event-id XXX --start 2026-09-14T16:00 --duration 60 --yes    # 执行
    python scripts/update_event.py --event-id XXX --title "新标题" --location "新地点" --yes
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.conflicts import find_conflicts
from src.datetime_utils import get_tz, parse_iso, to_iso
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="修改日程（默认预览，--yes 执行）")
    parser.add_argument("--event-id", required=True, help="目标事件的 event id（来自 search_events）")
    parser.add_argument("--title", help="新标题（可选）")
    parser.add_argument("--start", metavar="ISO", help="新开始时间（ISO 8601，可选）")
    parser.add_argument("--end", metavar="ISO", help="新结束时间（与 --duration 二选一）")
    parser.add_argument("--duration", type=int, metavar="分钟", help="新持续时长（分钟，与 --end 二选一）")
    parser.add_argument("--location", help="新地点（传空字符串表示清空）")
    parser.add_argument("--description", help="新备注（传空字符串表示清空）")
    parser.add_argument("--yes", action="store_true", help="确认执行（缺省只预览）")
    args = parser.parse_args()

    has_time = bool(args.start or args.end or args.duration)
    if args.end is not None and args.duration is not None:
        parser.error("--end 与 --duration 必须二选一")
    if not (has_time or args.title is not None or args.location is not None
            or args.description is not None):
        parser.error("至少提供一项要修改的字段")

    try:
        service = get_calendar_service_class()()
        current = service.get_event(args.event_id)

        # 计算生效后的新时间（未提供的字段沿用当前值）
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

        # 时间有变化时做冲突检查（排除自身）
        conflicts = []
        if time_changed:
            nearby = service.list_events(new_start, new_end)
            conflicts = find_conflicts(nearby, new_start, new_end,
                                       exclude_event_id=args.event_id)

        tz = get_tz()
        print("原日程:")
        _print_event(current, tz)
        print("准备修改为:")
        _print_event({
            "title": args.title if args.title is not None else current["title"],
            "start": new_start,
            "end": new_end,
            "location": args.location if args.location is not None else current["location"],
            "description": (args.description if args.description is not None
                            else current["description"]),
        }, tz)

        if current.get("is_series_master"):
            print("\n⚠️ 这是重复日程的系列母事件：修改将影响整个系列（所有场次）。")
        elif current.get("series_master_id"):
            print("\n⚠️ 这是重复日程的其中一场：修改仅影响这一场。")

        if conflicts:
            print(f"\n⚠️ 新时间与 {len(conflicts)} 个已有日程冲突:")
            for ev in conflicts:
                print(f"  - [{_fmt(ev['start'], ev['end'], tz)}] {ev['title']}")
            print("如需仍要修改，请加 --yes 重新运行。")
            return 3

        if not args.yes:
            print("\n（预览模式，未实际修改。确认无误后加 --yes 执行。）")
            return 0

        updated = service.update_event(
            args.event_id,
            title=args.title,
            start=new_start if args.start or args.duration or args.end else None,
            end=new_end if args.end is not None or args.duration is not None else None,
            location=args.location,
            description=args.description,
        )
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    print("\n✅ 已修改日程:")
    _print_event(updated, get_tz())
    return 0


def _print_event(ev: dict, tz) -> None:
    print(f"- [{_fmt(ev['start'], ev['end'], tz)}] {ev['title']}")
    if ev.get("location"):
        print(f"    地点: {ev['location']}")
    description = (ev.get("description") or "").strip()
    if description:
        print(f"    备注: {description[:80]}" + ("…" if len(description) > 80 else ""))


def _fmt(start, end, tz) -> str:
    start, end = start.astimezone(tz), end.astimezone(tz)
    if start.date() == end.date():
        return f"{start:%Y-%m-%d %H:%M}~{end:%H:%M}"
    return f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"


if __name__ == "__main__":
    sys.exit(main())

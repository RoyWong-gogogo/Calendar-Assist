"""列出会议室（Exchange room mailbox）及其占用情况。

中国区 Graph 目前没有可用的会议室清单接口：
- GET /me/findRooms 需要额外委托权限（当前应用只有 Calendars.ReadWrite，返回 403）
- GET /places/microsoft.graph.room（Places API）在中国区未开放
因此本脚本按会议室邮箱的命名规律（前缀 + 编号 @ 域名）扫描编号区间，用
POST /me/calendar/getSchedule 确认哪些会议室真实存在，并列出时间窗内的占用。
前缀与域名见 src/config.py 的 ROOM_NAME_PREFIX / ROOM_EMAIL_DOMAIN（可用 .env 覆盖）。

用法（项目根目录）：
    python scripts/list_rooms.py                                # 今天，编号 800-850
    python scripts/list_rooms.py --date 2026-09-15
    python scripts/list_rooms.py --from 2026-09-15T10:00 --to 2026-09-15T11:00
    python scripts/list_rooms.py --first 800 --last 820 --json

Codex 也可以直接调用 service.scan_rooms()。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_PROVIDER, ROOM_EMAIL_DOMAIN, ROOM_NAME_PREFIX
from src.datetime_utils import day_bounds, get_tz, parse_iso, to_iso
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="列出会议室及其占用情况")
    parser.add_argument("--date", help="today | tomorrow | yesterday | YYYY-MM-DD（默认今天）")
    parser.add_argument("--from", dest="start", metavar="ISO", help="时间窗开始（ISO 8601）")
    parser.add_argument("--to", dest="end", metavar="ISO", help="时间窗结束（ISO 8601）")
    parser.add_argument("--first", type=int, default=800, help="编号区间起点（默认 800）")
    parser.add_argument("--last", type=int, default=850, help="编号区间终点（默认 850）")
    parser.add_argument("--prefix", help=f"会议室邮箱前缀（默认 {ROOM_NAME_PREFIX}）")
    parser.add_argument("--domain", help=f"会议室邮箱域名（默认 {ROOM_EMAIL_DOMAIN}）")
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

        service = get_calendar_service_class()()
        if not hasattr(service, "scan_rooms"):
            raise RuntimeError(
                f"当前后端（{CALENDAR_PROVIDER}）不支持查询会议室，"
                "请使用 Outlook 后端（.env 设置 CALENDAR_PROVIDER=outlook）"
            )
        rooms = service.scan_rooms(
            args.first, args.last, start, end,
            prefix=args.prefix, domain=args.domain,
        )
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    tz = get_tz()
    if args.json:
        print(json.dumps(
            {
                "range": {"start": to_iso(start), "end": to_iso(end)},
                "rooms": [
                    {
                        "address": room["address"],
                        "label": room["label"],
                        "busy_in_range": [
                            {"start": to_iso(s), "end": to_iso(e)}
                            for s, e in room["busy_in_range"]
                        ],
                        "free_in_range": not room["busy_in_range"],
                    }
                    for room in rooms
                ],
            },
            ensure_ascii=False, indent=2,
        ))
        return 0

    print(
        f"会议室邮箱: {args.prefix or ROOM_NAME_PREFIX}*"
        f"@{args.domain or ROOM_EMAIL_DOMAIN}（扫描编号 {args.first}-{args.last}）"
    )
    print(f"时间窗: {to_iso(start)} ~ {to_iso(end)}")
    if not rooms:
        print("（该编号区间内没有找到会议室）")
        return 0

    print(f"共 {len(rooms)} 间会议室:")
    for room in rooms:
        busy = room["busy_in_range"]
        if not busy:
            print(f"- {room['address']}   空闲")
            continue
        detail = ", ".join(
            f"{s.astimezone(tz):%H:%M}~{e.astimezone(tz):%H:%M}" for s, e in busy
        )
        print(f"- {room['address']}   占用 {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

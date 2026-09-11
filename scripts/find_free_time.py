"""在时间范围内查找满足时长的空闲区间。

用法（项目根目录）：
    python scripts/find_free_time.py --from 2026-09-14T09:00 --to 2026-09-14T18:00 --duration 60

Codex 负责把自然语言（如"下周三下午找个 1 小时空档"）换算成明确时间范围后
调用本脚本，也可以直接调用服务类的 find_free_time。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_PROVIDER
from src.datetime_utils import get_tz, parse_iso, to_iso
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="查找空闲时间")
    parser.add_argument("--from", dest="start", required=True, metavar="ISO", help="范围开始（ISO 8601）")
    parser.add_argument("--to", dest="end", required=True, metavar="ISO", help="范围结束（ISO 8601）")
    parser.add_argument("--duration", type=int, default=60, metavar="分钟", help="需要的时长（分钟，默认 60）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration 必须为正整数（分钟）")

    try:
        start = parse_iso(args.start)
        end = parse_iso(args.end)
        service = get_calendar_service_class()()
        slots = service.find_free_time(start, end, args.duration)
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([
            {"start": to_iso(s), "end": to_iso(e)} for s, e in slots
        ], ensure_ascii=False, indent=2))
        return 0

    tz = get_tz()
    print(f"日历: {service.calendar_id}（{CALENDAR_PROVIDER}） | 时区: {tz.key}")
    print(f"范围: {to_iso(start)} ~ {to_iso(end)} | 需要: {args.duration} 分钟")
    if not slots:
        print(f"（该范围内没有满足 {args.duration} 分钟的空闲时段）")
        return 0
    for slot_start, slot_end in slots:
        print(f"- {_format_slot(slot_start, slot_end, tz)}")
    return 0


def _format_slot(slot_start, slot_end, tz) -> str:
    start = slot_start.astimezone(tz)
    end = slot_end.astimezone(tz)
    minutes = int((end - start).total_seconds() // 60)
    if start.date() == end.date():
        return f"{start:%m-%d %H:%M}~{end:%H:%M}（{minutes} 分钟）"
    return f"{start:%m-%d %H:%M} ~ {end:%m-%d %H:%M}（{minutes} 分钟）"


if __name__ == "__main__":
    sys.exit(main())

"""删除日程（默认直接执行；--dry-run 才是预览）。

定位目标两种方式：
    --event-id XXX                        直接用 id（来自 search_events 或上次汇报）
    --query 关键词 --date tomorrow        脚本自己搜索定位（唯一命中即执行）

0 个命中或 ≥2 个候选会停下并要求澄清（退出码 4）；--yes 保留为兼容空参数。

用法（项目根目录）：
    python scripts/delete_event.py --event-id XXX
    python scripts/delete_event.py --query 客户会议 --date tomorrow
    python scripts/delete_event.py --event-id XXX --dry-run       # 只看不删
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datetime_utils import get_tz
from src.notices import event_line, print_candidates, print_event_detail, print_no_match
from src.service_factory import get_calendar_service_class
from src.targets import EXIT_NEEDS_CHOICE, locate_event, resolve_range


def main() -> int:
    parser = argparse.ArgumentParser(description="删除日程（默认执行，--dry-run 预览）")
    parser.add_argument("--event-id", help="目标事件的 event id（与 --query 二选一）")
    parser.add_argument("--query", help="关键词定位目标（标题/地点/备注，需唯一命中）")
    parser.add_argument("--date", help="定位搜索范围: today | tomorrow | yesterday | YYYY-MM-DD（默认今天）")
    parser.add_argument("--from", dest="range_from", metavar="ISO",
                        help="定位搜索范围开始（与 --to 成对；宁大勿小）")
    parser.add_argument("--to", dest="range_to", metavar="ISO",
                        help="定位搜索范围结束（与 --from 成对）")
    parser.add_argument("--dry-run", action="store_true", help="只预览不删除")
    parser.add_argument("--yes", action="store_true", help="兼容保留（现在默认即执行）")
    args = parser.parse_args()

    if bool(args.event_id) == bool(args.query):
        parser.error("--event-id 与 --query 必须二选一")

    try:
        service = get_calendar_service_class()()

        # 定位目标：按 id 直接读；按关键词先搜范围，再确认唯一命中
        if args.event_id:
            target = service.get_event(args.event_id)
        else:
            range_start, range_end = resolve_range(args.date, args.range_from, args.range_to)
            target, candidates = locate_event(service, args.query, range_start, range_end)
            if target is None:
                if not candidates:
                    print_no_match(args.query, range_start, range_end)
                else:
                    print_candidates(candidates)
                return EXIT_NEEDS_CHOICE
            if target.get("is_series_master"):
                print("⚠️ 关键词命中的是重复日程的系列母事件，删除会取消整个系列。")
                print(f"- {event_line(target, get_tz())}")
                print("请确认影响范围后，用 --event-id 明确指定再删。")
                return EXIT_NEEDS_CHOICE

        tz = get_tz()
        print("目标日程:")
        print(f"- {event_line(target, tz)}")
        print_event_detail(target)

        if target.get("is_series_master"):
            print("\n⚠️ 这是重复日程的系列母事件：删除将取消整个系列（所有场次）。")
        elif target.get("series_master_id"):
            print("\n⚠️ 这是重复日程的其中一场：删除仅取消这一场。")

        if args.dry_run:
            print("\n（--dry-run：未删除。去掉 --dry-run 即执行。）")
            return 0

        service.delete_event(target["id"])
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    print()
    print(f"✅ 已删除: {event_line(target, get_tz())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


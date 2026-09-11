"""删除日程（安全模式：默认只展示目标，--yes 才真正删除）。

必须通过真实 event id 删除（可先用 scripts/search_events.py 找到候选）。
Codex 使用流程：搜索 → 匹配候选（多个时让用户选）→ 展示目标 →
用户确认 → 带 --yes 执行。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datetime_utils import get_tz
from src.service_factory import get_calendar_service_class


def main() -> int:
    parser = argparse.ArgumentParser(description="删除日程（默认预览，--yes 执行）")
    parser.add_argument("--event-id", required=True, help="目标事件的 event id（来自 search_events）")
    parser.add_argument("--yes", action="store_true", help="确认删除（缺省只预览）")
    args = parser.parse_args()

    try:
        service = get_calendar_service_class()()
        target = service.get_event(args.event_id)

        tz = get_tz()
        print("准备删除以下日程:")
        start, end = target["start"].astimezone(tz), target["end"].astimezone(tz)
        if target["all_day"]:
            time_range = f"{start:%Y-%m-%d} 全天"
        elif start.date() == end.date():
            time_range = f"{start:%Y-%m-%d %H:%M}~{end:%H:%M}"
        else:
            time_range = f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}"
        print(f"- [{time_range}] {target['title']}")
        if target["location"]:
            print(f"    地点: {target['location']}")

        if target.get("is_series_master"):
            print("\n⚠️ 这是重复日程的系列母事件：删除将取消整个系列（所有场次）。")
        elif target.get("series_master_id"):
            print("\n⚠️ 这是重复日程的其中一场：删除仅取消这一场。")

        if not args.yes:
            print("\n（预览模式，未实际删除。确认后加 --yes 执行。）")
            return 0

        service.delete_event(args.event_id)
    except RuntimeError as exc:
        print(f"[日历错误] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[参数错误] {exc}", file=sys.stderr)
        return 2

    print("\n✅ 已删除。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

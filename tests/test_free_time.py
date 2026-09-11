"""find_free_slots 纯算法的单元测试（不需要网络，也不需要任何凭证）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.free_time import find_free_slots

TZ = ZoneInfo(CALENDAR_TIMEZONE)
ONE_HOUR = timedelta(minutes=60)


def _dt(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


def _event(day, start_hour, end_hour, start_min=0, end_min=0):
    return {
        "id": f"{day}-{start_hour}-{start_min}",
        "title": "忙",
        "start": _dt(day, start_hour, start_min),
        "end": _dt(day, end_hour, end_min),
        "all_day": False,
        "location": None,
        "description": None,
    }


class FindFreeSlotsTests(unittest.TestCase):
    def test_empty_calendar_whole_window_free(self):
        slots = find_free_slots([], _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 18))])

    def test_single_event_splits_window(self):
        busy = [_event(14, 12, 13)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(
            slots, [(_dt(14, 9), _dt(14, 12)), (_dt(14, 13), _dt(14, 18))]
        )

    def test_overlapping_events_merged(self):
        busy = [_event(14, 12, 13), _event(14, 12, 14, start_min=30)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 12)), (_dt(14, 14), _dt(14, 18))])

    def test_adjacent_events_leave_no_gap(self):
        busy = [_event(14, 9, 10), _event(14, 10, 11)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 11), _dt(14, 18))])

    def test_event_clipped_to_window(self):
        # 事件 8:30-9:30 越过窗口左边界，裁剪后窗口从 9:30 起空闲
        busy = [_event(14, 8, 9, end_min=30)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9, 30), _dt(14, 18))])

    def test_event_outside_window_ignored(self):
        busy = [_event(14, 19, 20)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 18))])

    def test_all_day_event_blocks_everything(self):
        # 全天事件：9/14 00:00 ~ 9/15 00:00（次日 0 点表示当天结束）
        busy = [{
            "id": "allday", "title": "全天",
            "start": _dt(14, 0), "end": _dt(15, 0),
            "all_day": True, "location": None, "description": None,
        }]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [])

    def test_gap_shorter_than_duration_excluded(self):
        # 12:00-12:30 只有 30 分钟空隙，放不下 60 分钟
        busy = [_event(14, 9, 12), _event(14, 12, 18, start_min=30)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [])

    def test_none_times_ignored(self):
        busy = [{"id": "x", "title": "时间未知", "start": None, "end": None,
                 "all_day": False, "location": None, "description": None}]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 18))])

    def test_zero_length_event_ignored(self):
        busy = [_event(14, 12, 12)]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 18))])

    def test_multi_day_window(self):
        busy = [{
            "id": "allday", "title": "全天",
            "start": _dt(14, 0), "end": _dt(15, 0),
            "all_day": True, "location": None, "description": None,
        }]
        slots = find_free_slots(busy, _dt(14, 9), _dt(15, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(15, 0), _dt(15, 18))])

    def test_mixed_timezones_equivalent(self):
        # 12:00+08:00 == 04:00Z，结果应与本地时间事件一致
        busy = [{
            "id": "utc", "title": "UTC 事件",
            "start": datetime(2026, 9, 14, 4, 0, tzinfo=ZoneInfo("UTC")),
            "end": datetime(2026, 9, 14, 5, 0, tzinfo=ZoneInfo("UTC")),
            "all_day": False, "location": None, "description": None,
        }]
        slots = find_free_slots(busy, _dt(14, 9), _dt(14, 18), ONE_HOUR)
        self.assertEqual(slots, [(_dt(14, 9), _dt(14, 12)), (_dt(14, 13), _dt(14, 18))])

    def test_invalid_duration_raises(self):
        for bad in (timedelta(0), timedelta(minutes=-30)):
            with self.assertRaises(ValueError):
                find_free_slots([], _dt(14, 9), _dt(14, 18), bad)

    def test_invalid_window_raises(self):
        with self.assertRaises(ValueError):
            find_free_slots([], _dt(14, 18), _dt(14, 9), ONE_HOUR)


if __name__ == "__main__":
    unittest.main()

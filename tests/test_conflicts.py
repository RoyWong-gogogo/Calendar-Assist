"""find_conflicts 纯算法的单元测试。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.conflicts import find_conflicts

TZ = ZoneInfo(CALENDAR_TIMEZONE)


def _event(event_id, start, end):
    return {"id": event_id, "title": event_id, "start": start, "end": end,
            "all_day": False, "location": None, "description": None}


def _dt(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


class FindConflictsTests(unittest.TestCase):
    def test_no_overlap_no_conflict(self):
        events = [_event("a", _dt(14, 9), _dt(14, 10))]
        result = find_conflicts(events, _dt(14, 11), _dt(14, 12))
        self.assertEqual(result, [])

    def test_exact_overlap_is_conflict(self):
        events = [_event("a", _dt(14, 15), _dt(14, 16))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(len(result), 1)

    def test_partial_overlap_is_conflict(self):
        events = [_event("a", _dt(14, 15, 30), _dt(14, 16, 30))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(len(result), 1)

    def test_event_contains_range_is_conflict(self):
        events = [_event("a", _dt(14, 14), _dt(14, 17))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(len(result), 1)

    def test_touching_boundary_is_not_conflict(self):
        # 15:00-16:00 与 16:00-17:00 首尾相接，不算冲突
        events = [_event("a", _dt(14, 16), _dt(14, 17))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(result, [])

    def test_exclude_self(self):
        # 移动自身事件时排除自己：14:00-15:00 改到 14:30-15:30
        events = [_event("me", _dt(14, 14), _dt(14, 15)),
                  _event("other", _dt(14, 15), _dt(14, 16))]
        result = find_conflicts(events, _dt(14, 14, 30), _dt(14, 15, 30),
                                exclude_event_id="me")
        self.assertEqual([ev["id"] for ev in result], ["other"])

    def test_without_exclude_self_is_conflict(self):
        # 对照：不排除时自己也算冲突
        events = [_event("me", _dt(14, 14), _dt(14, 15))]
        result = find_conflicts(events, _dt(14, 14, 30), _dt(14, 15, 30))
        self.assertEqual(len(result), 1)

    def test_all_day_event_conflicts_with_any_time(self):
        events = [_event("allday", _dt(14, 0), _dt(15, 0))]
        result = find_conflicts(events, _dt(14, 10), _dt(14, 11))
        self.assertEqual(len(result), 1)

    def test_none_and_zero_length_ignored(self):
        events = [
            {"id": "none", "title": "x", "start": None, "end": None,
             "all_day": False, "location": None, "description": None},
            _event("zero", _dt(14, 15), _dt(14, 15)),
        ]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(result, [])

    def test_multiple_conflicts_order_preserved(self):
        events = [_event("b", _dt(14, 15), _dt(14, 16)),
                  _event("a", _dt(14, 15, 30), _dt(14, 17))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 18))
        self.assertEqual([ev["id"] for ev in result], ["b", "a"])

    def test_mixed_timezones_equivalent(self):
        # 15:00+08:00 == 07:00Z，应判为冲突
        utc = ZoneInfo("UTC")
        events = [_event("utc", datetime(2026, 9, 14, 7, tzinfo=utc),
                         datetime(2026, 9, 14, 8, tzinfo=utc))]
        result = find_conflicts(events, _dt(14, 15), _dt(14, 16))
        self.assertEqual(len(result), 1)

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            find_conflicts([], _dt(14, 16), _dt(14, 15))


if __name__ == "__main__":
    unittest.main()

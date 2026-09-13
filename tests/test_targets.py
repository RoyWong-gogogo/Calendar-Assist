"""src/targets.py 的单元测试（用桩服务，不碰网络也不碰真实日历）。"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.targets import EXIT_NEEDS_CHOICE, locate_event, resolve_range

TZ = ZoneInfo(CALENDAR_TIMEZONE)


def _event(event_id: str, title: str, hour: int = 15) -> dict:
    return {
        "id": event_id,
        "title": title,
        "start": datetime(2026, 9, 14, hour, 0, tzinfo=TZ),
        "end": datetime(2026, 9, 14, hour + 1, 0, tzinfo=TZ),
        "all_day": False,
        "location": None,
        "description": None,
    }


class _StubService:
    def __init__(self, events):
        self.events = events
        self.calls: list[tuple[datetime, datetime]] = []

    def list_events(self, start, end):
        self.calls.append((start, end))
        return list(self.events)


class ResolveRangeTests(unittest.TestCase):
    def test_explicit_from_to(self):
        start, end = resolve_range(None, "2026-09-14T12:00", "2026-09-14T18:00")
        self.assertEqual((start.hour, end.hour), (12, 18))

    def test_date_keyword(self):
        start, end = resolve_range("2026-09-14", None, None)
        self.assertEqual(start.date(), date(2026, 9, 14))
        self.assertEqual(start.hour, 0)
        self.assertEqual(end.date(), date(2026, 9, 15))

    def test_default_is_today(self):
        start, end = resolve_range(None, None, None)
        self.assertLess(start, end)
        self.assertEqual(start.hour, 0)

    def test_half_pair_raises(self):
        with self.assertRaises(ValueError):
            resolve_range(None, "2026-09-14T12:00", None)
        with self.assertRaises(ValueError):
            resolve_range(None, None, "2026-09-14T18:00")

    def test_date_and_range_conflict_raises(self):
        with self.assertRaises(ValueError):
            resolve_range("2026-09-14", "2026-09-14T12:00", "2026-09-14T18:00")


class LocateEventTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
        self.end = datetime(2026, 9, 14, 18, 0, tzinfo=TZ)

    def test_unique_match_returns_target(self):
        service = _StubService([_event("id-1", "和壁仞的会议"), _event("id-2", "周会")])
        target, candidates = locate_event(service, "壁仞", self.start, self.end)
        self.assertIsNotNone(target)
        self.assertEqual(target["id"], "id-1")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(service.calls, [(self.start, self.end)])

    def test_no_match_returns_none_and_empty(self):
        service = _StubService([_event("id-1", "周会")])
        target, candidates = locate_event(service, "壁仞", self.start, self.end)
        self.assertIsNone(target)
        self.assertEqual(candidates, [])

    def test_multiple_matches_stop_without_guessing(self):
        service = _StubService([_event("id-1", "客户会议 A"), _event("id-2", "客户会议 B")])
        target, candidates = locate_event(service, "客户会议", self.start, self.end)
        self.assertIsNone(target)
        self.assertEqual([ev["id"] for ev in candidates], ["id-1", "id-2"])

    def test_exit_code_for_human_decision(self):
        self.assertEqual(EXIT_NEEDS_CHOICE, 4)


if __name__ == "__main__":
    unittest.main()


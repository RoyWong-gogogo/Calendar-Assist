"""ICS 解析的单元测试（不需要网络，也不需要真实订阅链接）。"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.ics_service import IcsCalendarService, IcsError


ICS_SAMPLE = "\r\n".join([
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//calendar-agent//test//EN",
    "BEGIN:VEVENT",
    "UID:normal-1",
    "SUMMARY:和王总开会",
    "DTSTART:20260910T070000Z",
    "DTEND:20260910T080000Z",
    "LOCATION:会议室 A",
    "DESCRIPTION:季度 review",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:allday-1",
    "SUMMARY:休假",
    "DTSTART;VALUE=DATE:20260910",
    "DTEND;VALUE=DATE:20260911",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:float-1",
    "SUMMARY:浮动时间事件",
    "DTSTART:20260910T090000",
    "DTEND:20260910T093000",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:dur-1",
    "SUMMARY:带时长事件",
    "DTSTART:20260910T020000Z",
    "DURATION:PT45M",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:daily-1",
    "SUMMARY:每日站会",
    "DTSTART:20260910T010000Z",
    "DTEND:20260910T013000Z",
    "RRULE:FREQ=DAILY;COUNT=5",
    "END:VEVENT",
    "END:VCALENDAR",
])


class IcsParsingTests(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo(CALENDAR_TIMEZONE)
        self.service = IcsCalendarService()

    def _parse(self, start_day: date, end_day: date) -> list[dict]:
        start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=self.tz)
        end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=self.tz)
        return self.service._parse(ICS_SAMPLE, start, end)

    def test_single_day_window_contains_all_event_kinds(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 11))
        self.assertEqual(len(events), 5)
        self.assertEqual(
            {ev["id"] for ev in events},
            {"normal-1", "allday-1", "float-1", "dur-1", "daily-1"},
        )

    def test_fields_mapping(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 11))
        normal = next(ev for ev in events if ev["id"] == "normal-1")
        self.assertEqual(normal["title"], "和王总开会")
        self.assertEqual(normal["location"], "会议室 A")
        self.assertEqual(normal["description"], "季度 review")
        self.assertEqual(
            normal["start"].astimezone(self.tz),
            datetime(2026, 9, 10, 15, 0, tzinfo=self.tz),
        )
        self.assertEqual(
            normal["end"].astimezone(self.tz),
            datetime(2026, 9, 10, 16, 0, tzinfo=self.tz),
        )
        self.assertFalse(normal["all_day"])

    def test_all_day_event(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 11))
        allday = next(ev for ev in events if ev["id"] == "allday-1")
        self.assertTrue(allday["all_day"])
        self.assertEqual(allday["start"].astimezone(self.tz).date(), date(2026, 9, 10))
        self.assertEqual(allday["end"].astimezone(self.tz).date(), date(2026, 9, 11))

    def test_floating_time_interpreted_in_config_tz(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 11))
        floating = next(ev for ev in events if ev["id"] == "float-1")
        self.assertEqual(
            floating["start"].utcoffset(), self.tz.utcoffset(floating["start"])
        )
        self.assertEqual(floating["start"].hour, 9)
        self.assertEqual(floating["end"].minute, 30)

    def test_duration_only_event(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 11))
        dur = next(ev for ev in events if ev["id"] == "dur-1")
        self.assertEqual(dur["end"] - dur["start"], timedelta(minutes=45))

    def test_recurring_events_expanded(self):
        # RRULE COUNT=5：9/10-9/14 每天一场（01:00Z = 09:00+08）
        events = self._parse(date(2026, 9, 10), date(2026, 9, 15))
        daily = [ev for ev in events if ev["id"] == "daily-1"]
        self.assertEqual(len(daily), 5)
        starts = [ev["start"].astimezone(self.tz) for ev in daily]
        self.assertEqual(starts[0], datetime(2026, 9, 10, 9, 0, tzinfo=self.tz))
        self.assertEqual(starts[-1], datetime(2026, 9, 14, 9, 0, tzinfo=self.tz))

    def test_window_filters_events(self):
        events = self._parse(date(2026, 9, 12), date(2026, 9, 13))
        self.assertEqual([ev["id"] for ev in events], ["daily-1"])

    def test_events_sorted_by_start(self):
        events = self._parse(date(2026, 9, 10), date(2026, 9, 15))
        starts = [ev["start"] for ev in events]
        self.assertEqual(starts, sorted(starts))

    def test_list_events_requires_ics_url(self):
        start = datetime(2026, 9, 10, tzinfo=self.tz)
        end = datetime(2026, 9, 11, tzinfo=self.tz)
        with mock.patch("src.ics_service.ICS_URL", ""):
            with self.assertRaises(IcsError):
                self.service.list_events(start, end)

    def test_invalid_range_raises_value_error(self):
        start = datetime(2026, 9, 11, tzinfo=self.tz)
        end = datetime(2026, 9, 10, tzinfo=self.tz)
        with self.assertRaises(ValueError):
            self.service.list_events(start, end)


if __name__ == "__main__":
    unittest.main()

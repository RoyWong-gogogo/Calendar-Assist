"""datetime_utils 的单元测试（不需要网络，也不需要 Google 凭证）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.datetime_utils import day_bounds, ensure_aware, parse_iso, resolve_day, to_iso


class DatetimeUtilsTests(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo(CALENDAR_TIMEZONE)

    def test_ensure_aware_naive_datetime_gets_configured_tz(self):
        dt = ensure_aware(datetime(2026, 9, 10, 15, 0))
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.utcoffset(), self.tz.utcoffset(dt))

    def test_ensure_aware_keeps_existing_tz(self):
        dt = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
        self.assertEqual(ensure_aware(dt), dt)

    def test_parse_iso_naive_interpreted_in_config_tz(self):
        dt = parse_iso("2026-09-10T15:00")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour), (2026, 9, 10, 15))
        self.assertEqual(dt.utcoffset(), self.tz.utcoffset(dt))

    def test_parse_iso_with_offset(self):
        dt = parse_iso("2026-09-10T15:00+08:00")
        self.assertEqual(dt.utcoffset().total_seconds(), 8 * 3600)

    def test_parse_iso_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_iso("not-a-date")

    def test_to_iso_roundtrip(self):
        dt = parse_iso("2026-09-10T15:00+08:00")
        self.assertEqual(parse_iso(to_iso(dt)), dt)

    def test_day_bounds_covers_whole_day_in_config_tz(self):
        start, end = day_bounds("2026-09-10")
        self.assertEqual(start, datetime(2026, 9, 10, 0, 0, tzinfo=self.tz))
        self.assertEqual(end, datetime(2026, 9, 11, 0, 0, tzinfo=self.tz))

    def test_resolve_day_keywords(self):
        today = resolve_day(None)
        self.assertEqual(resolve_day("today"), today)
        self.assertEqual(resolve_day("tomorrow"), today + timedelta(days=1))
        self.assertEqual(resolve_day("yesterday"), today - timedelta(days=1))

    def test_resolve_day_iso_date(self):
        self.assertEqual(resolve_day("2026-09-10").isoformat(), "2026-09-10")

    def test_resolve_day_invalid_raises(self):
        # 复杂自然语言（如“下周三”）不属于这里，由 Codex 负责换算
        with self.assertRaises(ValueError):
            resolve_day("next wednesday")


if __name__ == "__main__":
    unittest.main()

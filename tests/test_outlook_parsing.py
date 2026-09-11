"""Outlook Graph 时间解析的单元测试（不需要网络，也不需要微软凭证）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.outlook_service import _strip_html, _to_event_dict, parse_graph_datetime


class ParseGraphDatetimeTests(unittest.TestCase):
    def test_naive_with_iana_timezone_field(self):
        dt = parse_graph_datetime(
            {"dateTime": "2026-09-10T09:00:00.0000000", "timeZone": "Asia/Shanghai"}
        )
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.utcoffset().total_seconds(), 8 * 3600)

    def test_naive_with_windows_timezone_falls_back_to_configured(self):
        dt = parse_graph_datetime(
            {"dateTime": "2026-09-10T09:00:00.0000000", "timeZone": "China Standard Time"}
        )
        expected = ZoneInfo(CALENDAR_TIMEZONE)
        self.assertEqual(dt.utcoffset(), expected.utcoffset(dt))

    def test_utc_with_z_and_seven_fraction_digits(self):
        dt = parse_graph_datetime(
            {"dateTime": "2026-09-10T01:00:00.0000000Z", "timeZone": "UTC"}
        )
        self.assertEqual(dt, datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc))

    def test_plain_z_suffix(self):
        dt = parse_graph_datetime({"dateTime": "2026-09-10T01:00:00Z", "timeZone": "UTC"})
        self.assertEqual(dt, datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc))

    def test_explicit_offset(self):
        dt = parse_graph_datetime(
            {"dateTime": "2026-09-10T09:00:00+08:00", "timeZone": "Asia/Shanghai"}
        )
        self.assertEqual(dt.utcoffset().total_seconds(), 8 * 3600)

    def test_fraction_plus_offset_preserved(self):
        dt = parse_graph_datetime(
            {"dateTime": "2026-09-10T09:00:00.0000000+08:00", "timeZone": "Asia/Shanghai"}
        )
        self.assertEqual(dt.utcoffset().total_seconds(), 8 * 3600)

    def test_none_and_invalid_values(self):
        self.assertIsNone(parse_graph_datetime(None))
        self.assertIsNone(parse_graph_datetime({}))
        self.assertIsNone(parse_graph_datetime({"timeZone": "UTC"}))


class EventDictTests(unittest.TestCase):
    def test_to_event_dict_maps_graph_fields(self):
        item = {
            "id": "abc123",
            "subject": "和王总开会",
            "start": {"dateTime": "2026-09-10T15:00:00.0000000", "timeZone": "Asia/Shanghai"},
            "end": {"dateTime": "2026-09-10T16:00:00.0000000", "timeZone": "Asia/Shanghai"},
            "isAllDay": False,
            "location": {"displayName": "会议室 A"},
            "body": {"contentType": "html", "content": "<p>带<BR>议程</p>"},
        }
        ev = _to_event_dict(item)
        self.assertEqual(ev["id"], "abc123")
        self.assertEqual(ev["title"], "和王总开会")
        self.assertEqual(ev["start"].hour, 15)
        self.assertFalse(ev["all_day"])
        self.assertEqual(ev["location"], "会议室 A")
        self.assertEqual(ev["description"], "带 议程")

    def test_all_day_event(self):
        item = {
            "id": "x",
            "subject": "休假",
            "start": {"dateTime": "2026-09-10T00:00:00.0000000", "timeZone": "Asia/Shanghai"},
            "end": {"dateTime": "2026-09-11T00:00:00.0000000", "timeZone": "Asia/Shanghai"},
            "isAllDay": True,
            "location": {},
            "body": {},
        }
        ev = _to_event_dict(item)
        self.assertTrue(ev["all_day"])
        self.assertIsNone(ev["location"])
        self.assertIsNone(ev["description"])

    def test_strip_html(self):
        self.assertEqual(_strip_html("<p>hello <b>world</b></p>"), "hello world")

    def test_strip_html_decodes_entities(self):
        # Outlook 空正文常为 "&nbsp;"，应解码为空白并返回 None
        self.assertEqual(_strip_html("<p>a&nbsp;b</p>"), "a b")

    def test_strip_html_empty_returns_none(self):
        self.assertIsNone(_strip_html("&nbsp;"))
        self.assertIsNone(_strip_html("<p> </p>"))


if __name__ == "__main__":
    unittest.main()

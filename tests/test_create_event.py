"""create_event 的单元测试（mock 掉网络与认证，不需要真实凭证）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.calendar_service import CalendarService
from src.ics_service import IcsCalendarService, IcsError
from src.outlook_service import OutlookApiError, OutlookCalendarService

TZ = ZoneInfo(CALENDAR_TIMEZONE)


def _graph_created_event():
    return {
        "id": "aaa-111",
        "subject": "和王总开会",
        "start": {"dateTime": "2026-09-14T15:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "end": {"dateTime": "2026-09-14T16:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "isAllDay": False,
        "location": {"displayName": "会议室 A"},
        "body": {"contentType": "html", "content": "<p>季度 review</p>"},
    }


class OutlookCreateEventTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()

    def _create(self, **kwargs):
        with mock.patch(
            "src.outlook_service._headers",
            return_value={"Authorization": "Bearer test"},
        ), mock.patch("src.outlook_service.requests.post") as post:
            post.return_value.status_code = 201
            post.return_value.json.return_value = _graph_created_event()
            event = self.service.create_event(**kwargs)
        return event, post

    def test_request_body_uses_local_datetime_and_timezone(self):
        _, post = self._create(
            title="和王总开会",
            start=datetime(2026, 9, 14, 15, 0, tzinfo=TZ),
            end=datetime(2026, 9, 14, 16, 0, tzinfo=TZ),
            location="会议室 A",
            description="季度 review",
        )
        self.assertIn("/me/events", post.call_args.args[0])
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["subject"], "和王总开会")
        self.assertEqual(
            body["start"],
            {"dateTime": "2026-09-14T15:00:00", "timeZone": CALENDAR_TIMEZONE},
        )
        self.assertEqual(
            body["end"],
            {"dateTime": "2026-09-14T16:00:00", "timeZone": CALENDAR_TIMEZONE},
        )
        self.assertEqual(body["location"], {"displayName": "会议室 A"})
        self.assertEqual(body["body"], {"contentType": "text", "content": "季度 review"})

    def test_utc_datetime_converted_to_configured_timezone(self):
        # 07:00Z = 15:00 +08:00
        _, post = self._create(
            title="跨时区",
            start=datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc),
            end=datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc),
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["start"]["dateTime"], "2026-09-14T15:00:00")
        self.assertEqual(body["end"]["dateTime"], "2026-09-14T16:00:00")

    def test_success_returns_event_dict(self):
        event, _ = self._create(
            title="和王总开会",
            start=datetime(2026, 9, 14, 15, 0, tzinfo=TZ),
            end=datetime(2026, 9, 14, 16, 0, tzinfo=TZ),
        )
        self.assertEqual(event["id"], "aaa-111")
        self.assertEqual(event["title"], "和王总开会")
        self.assertEqual(event["start"].hour, 15)
        self.assertEqual(event["location"], "会议室 A")
        self.assertEqual(event["description"], "季度 review")

    def test_http_error_raises_with_details(self):
        with mock.patch(
            "src.outlook_service._headers",
            return_value={"Authorization": "Bearer t"},
        ), mock.patch("src.outlook_service.requests.post") as post:
            post.return_value.status_code = 400
            post.return_value.text = "invalid start"
            with self.assertRaises(OutlookApiError) as ctx:
                self.service.create_event(
                    title="x",
                    start=datetime(2026, 9, 14, 15, 0, tzinfo=TZ),
                    end=datetime(2026, 9, 14, 16, 0, tzinfo=TZ),
                )
        self.assertIn("400", str(ctx.exception))
        self.assertIn("invalid start", str(ctx.exception))

    def test_empty_title_raises(self):
        with self.assertRaises(ValueError):
            self.service.create_event(
                title="   ",
                start=datetime(2026, 9, 14, 15, 0, tzinfo=TZ),
                end=datetime(2026, 9, 14, 16, 0, tzinfo=TZ),
            )

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            self.service.create_event(
                title="x",
                start=datetime(2026, 9, 14, 16, 0, tzinfo=TZ),
                end=datetime(2026, 9, 14, 15, 0, tzinfo=TZ),
            )

    def test_find_free_time_delegates_to_list_events(self):
        busy = [{
            "id": "b1", "title": "忙",
            "start": datetime(2026, 9, 14, 12, 0, tzinfo=TZ),
            "end": datetime(2026, 9, 14, 13, 0, tzinfo=TZ),
            "all_day": False, "location": None, "description": None,
        }]
        with mock.patch.object(self.service, "list_events", return_value=busy):
            slots = self.service.find_free_time(
                datetime(2026, 9, 14, 9, 0, tzinfo=TZ),
                datetime(2026, 9, 14, 18, 0, tzinfo=TZ),
                60,
            )
        self.assertEqual(slots, [
            (datetime(2026, 9, 14, 9, 0, tzinfo=TZ), datetime(2026, 9, 14, 12, 0, tzinfo=TZ)),
            (datetime(2026, 9, 14, 13, 0, tzinfo=TZ), datetime(2026, 9, 14, 18, 0, tzinfo=TZ)),
        ])


class OtherBackendsCreateEventTests(unittest.TestCase):
    def test_ics_backend_rejects_create(self):
        start = datetime(2026, 9, 14, 15, 0, tzinfo=TZ)
        end = datetime(2026, 9, 14, 16, 0, tzinfo=TZ)
        with self.assertRaises(IcsError):
            IcsCalendarService().create_event(title="x", start=start, end=end)

    def test_google_backend_rejects_create(self):
        start = datetime(2026, 9, 14, 15, 0, tzinfo=TZ)
        end = datetime(2026, 9, 14, 16, 0, tzinfo=TZ)
        # Google 服务构造时会尝试 OAuth（必然失败），这里跳过构造只测方法
        with mock.patch.object(CalendarService, "__init__", lambda self: None):
            service = CalendarService()
            with self.assertRaises(NotImplementedError):
                service.create_event(title="x", start=start, end=end)


if __name__ == "__main__":
    unittest.main()

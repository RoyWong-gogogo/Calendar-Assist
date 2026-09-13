"""src/notices.py 的单元测试（捕获 stdout，用桩服务，不碰网络）。"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE, ROOM_EMAIL_DOMAIN, ROOM_NAME_PREFIX
from src.notices import (
    event_line,
    format_range,
    print_attendees,
    print_candidates,
    print_conflict_notice,
    print_no_match,
    print_room_notice,
    room_response,
)

TZ = ZoneInfo(CALENDAR_TIMEZONE)
ROOM_801 = f"{ROOM_NAME_PREFIX}801@{ROOM_EMAIL_DOMAIN}"


def _capture(func, *args, **kwargs):
    """执行函数并返回 (stdout 文本, 返回值)。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return buffer.getvalue(), result


def _event(event_id: str = "id-1", title: str = "周会", hour: int = 15,
           all_day: bool = False) -> dict:
    return {
        "id": event_id,
        "title": title,
        "start": datetime(2026, 9, 14, hour, 0, tzinfo=TZ),
        "end": datetime(2026, 9, 14, hour + 1, 0, tzinfo=TZ),
        "all_day": all_day,
        "location": None,
        "description": None,
        "rooms": [],
    }


class _StubService:
    def __init__(self, events=None, error: Exception | None = None):
        self.events = events or []
        self.error = error

    def list_events(self, start, end):
        if self.error:
            raise self.error
        return list(self.events)


class FormatTests(unittest.TestCase):
    def test_same_day_and_cross_day(self):
        same = format_range(datetime(2026, 9, 14, 15, tzinfo=TZ),
                            datetime(2026, 9, 14, 16, tzinfo=TZ), TZ)
        self.assertEqual(same, "2026-09-14 15:00~16:00")
        cross = format_range(datetime(2026, 9, 14, 23, tzinfo=TZ),
                             datetime(2026, 9, 15, 1, tzinfo=TZ), TZ)
        self.assertIn(" ~ ", cross)

    def test_all_day_and_missing(self):
        self.assertEqual(
            format_range(datetime(2026, 9, 14, 0, tzinfo=TZ),
                         datetime(2026, 9, 15, 0, tzinfo=TZ), TZ, all_day=True),
            "2026-09-14 全天",
        )
        self.assertEqual(format_range(None, None, TZ), "时间未知")

    def test_event_line(self):
        self.assertEqual(event_line(_event(), TZ), "[2026-09-14 15:00~16:00] 周会")


class ConflictNoticeTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 14, 15, 0, tzinfo=TZ)
        self.end = datetime(2026, 9, 14, 16, 0, tzinfo=TZ)

    def test_reports_overlap_but_excludes_self(self):
        service = _StubService([
            _event("moved", "被改的会", hour=15),
            _event("other", "别的会", hour=15),
        ])
        text, conflicts = _capture(
            print_conflict_notice, service, self.start, self.end, exclude_event_id="moved"
        )
        self.assertIn("还有 1 个日程", text)
        self.assertIn("别的会", text)
        self.assertNotIn("被改的会", text)
        self.assertEqual([ev["id"] for ev in conflicts], ["other"])

    def test_clear_slot_reports_single_line(self):
        service = _StubService([_event("far", "上午的会", hour=9)])
        text, conflicts = _capture(
            print_conflict_notice, service, self.start, self.end
        )
        self.assertEqual(conflicts, [])
        self.assertIn("该时段没有其它日程", text)

    def test_read_failure_does_not_raise(self):
        service = _StubService(error=RuntimeError("网络断了"))
        text, conflicts = _capture(
            print_conflict_notice, service, self.start, self.end
        )
        self.assertEqual(conflicts, [])
        self.assertIn("未能核对", text)


class RoomNoticeTests(unittest.TestCase):
    def _event_with_room(self, response):
        ev = _event(title="投资人访谈")
        ev["rooms"] = [ROOM_801]
        ev["room_responses"] = [{"type": "resource", "address": ROOM_801,
                                 "name": ROOM_NAME_PREFIX + "801", "response": response}]
        return ev

    def test_room_response_lookup(self):
        ev = self._event_with_room("accepted")
        self.assertEqual(room_response(ev, ROOM_801), "accepted")
        self.assertIsNone(room_response(ev, "other@arraycomm.com"))

    def test_accepted_is_reported_as_confirmed(self):
        text, response = _capture(print_room_notice, self._event_with_room("accepted"), ROOM_801)
        self.assertEqual(response, "accepted")
        self.assertIn("已接受", text)

    def test_declined_warns_to_change_room(self):
        text, _ = _capture(print_room_notice, self._event_with_room("declined"), ROOM_801)
        self.assertIn("请换一间", text)

    def test_pending_response_is_not_alarming(self):
        text, _ = _capture(print_room_notice, self._event_with_room("none"), ROOM_801)
        self.assertIn("尚未响应", text)

    def test_missing_room_in_response_warns(self):
        text, response = _capture(print_room_notice, _event(title="没带会议室"), ROOM_801)
        self.assertIsNone(response)
        self.assertIn("尚未响应", text)


class AttendeeReportTests(unittest.TestCase):
    def _event_with_people(self):
        ev = _event(title="AI 工具汇报")
        ev["attendees"] = [
            {"type": "required", "address": "emma.zhou@arraycomm.com",
             "name": "Emma Zhou", "response": "accepted"},
            {"type": "required", "address": "nzhou@arraycomm.com",
             "name": "Nanqing Zhou", "response": "none"},
            {"type": "resource", "address": ROOM_801,
             "name": ROOM_NAME_PREFIX + "801", "response": "accepted"},
        ]
        return ev

    def test_lists_people_with_response_but_not_room(self):
        text, _ = _capture(print_attendees, self._event_with_people())
        self.assertIn("Emma Zhou <emma.zhou@arraycomm.com>（accepted）", text)
        self.assertIn("Nanqing Zhou <nzhou@arraycomm.com>", text)
        self.assertNotIn("（none）", text)
        self.assertNotIn(ROOM_801, text)

    def test_no_people_prints_nothing(self):
        text, _ = _capture(print_attendees, _event())
        self.assertEqual(text, "")


class CandidateReportTests(unittest.TestCase):
    def test_candidates_listed_with_event_id(self):
        text, _ = _capture(print_candidates, [_event("id-1"), _event("id-2", "客户会")], TZ)
        self.assertIn("匹配到 2 个日程", text)
        self.assertIn("id-1", text)
        self.assertIn("id-2", text)

    def test_no_match_message_tells_range(self):
        text, _ = _capture(
            print_no_match, "壁仞",
            datetime(2026, 9, 14, 12, tzinfo=TZ), datetime(2026, 9, 14, 18, tzinfo=TZ),
        )
        self.assertIn("没有找到", text)
        self.assertIn("壁仞", text)
        self.assertIn("2026-09-14 12:00~18:00", text)


if __name__ == "__main__":
    unittest.main()


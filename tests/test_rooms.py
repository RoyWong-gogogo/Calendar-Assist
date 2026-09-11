"""会议室（Exchange room mailbox）相关单元测试（mock 网络与认证，无需真实凭证）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE, ROOM_EMAIL_DOMAIN, ROOM_NAME_PREFIX
from src.outlook_service import OutlookCalendarService
from src.rooms import expand_room, room_label

TZ = ZoneInfo(CALENDAR_TIMEZONE)
ROOM_801 = f"{ROOM_NAME_PREFIX}801@{ROOM_EMAIL_DOMAIN}"


def _room_attendee(address: str = ROOM_801) -> dict:
    return {"type": "resource",
            "emailAddress": {"address": address, "name": room_label(address)}}


def _graph_event(attendees=None) -> dict:
    return {
        "id": "evt-1",
        "subject": "锦江国投投资人访谈",
        "start": {"dateTime": "2026-09-15T10:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "end": {"dateTime": "2026-09-15T11:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "isAllDay": False,
        "location": {"displayName": room_label(ROOM_801)},
        "attendees": attendees or [],
    }


class ExpandRoomTests(unittest.TestCase):
    def test_number_expands_to_mailbox(self):
        self.assertEqual(expand_room("801"), ROOM_801)

    def test_name_expands_to_mailbox(self):
        self.assertEqual(
            expand_room(f"{ROOM_NAME_PREFIX}802"),
            f"{ROOM_NAME_PREFIX}802@{ROOM_EMAIL_DOMAIN}",
        )

    def test_full_address_is_kept(self):
        self.assertEqual(
            expand_room("CDConfRoom801@ArrayComm.com"), "CDConfRoom801@ArrayComm.com"
        )

    def test_unknown_name_raises(self):
        with self.assertRaises(ValueError):
            expand_room("三楼大会议室")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            expand_room("   ")

    def test_room_label(self):
        self.assertEqual(room_label(ROOM_801), f"{ROOM_NAME_PREFIX}801")


class CreateEventRoomTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()

    def _create(self, **kwargs):
        with mock.patch(
            "src.outlook_service._headers",
            return_value={"Authorization": "Bearer test"},
        ), mock.patch("src.outlook_service.requests.post") as post:
            post.return_value.status_code = 201
            post.return_value.json.return_value = _graph_event([_room_attendee()])
            event = self.service.create_event(**kwargs)
        return event, post

    def _slot_args(self, **extra):
        return dict(
            title="锦江国投投资人访谈",
            start=datetime(2026, 9, 15, 10, 0, tzinfo=TZ),
            end=datetime(2026, 9, 15, 11, 0, tzinfo=TZ),
            **extra,
        )

    def test_room_added_as_resource_attendee_with_location(self):
        _, post = self._create(**self._slot_args(room="801"))
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["attendees"], [_room_attendee()])
        self.assertEqual(body["location"]["displayName"], room_label(ROOM_801))
        self.assertEqual(body["location"]["locationEmailAddress"], ROOM_801)

    def test_explicit_location_wins_over_room_label(self):
        _, post = self._create(**self._slot_args(room="801", location="CD 会议室"))
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["location"]["displayName"], "CD 会议室")
        self.assertEqual(body["location"]["locationEmailAddress"], ROOM_801)

    def test_without_room_no_attendees(self):
        _, post = self._create(**self._slot_args(location="会议室 A"))
        body = post.call_args.kwargs["json"]
        self.assertNotIn("attendees", body)
        self.assertEqual(body["location"], {"displayName": "会议室 A"})

    def test_returned_event_exposes_rooms(self):
        event, _ = self._create(**self._slot_args(room="801"))
        self.assertEqual(event["rooms"], [ROOM_801])


class UpdateEventRoomTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()
        self.raw = {
            "id": "evt-1",
            "attendees": [
                {"type": "required",
                 "emailAddress": {"address": "guest@arraycomm.com"}},
                _room_attendee(f"{ROOM_NAME_PREFIX}808@{ROOM_EMAIL_DOMAIN}"),
            ],
        }

    def _update(self, **kwargs):
        with mock.patch(
            "src.outlook_service._headers",
            return_value={"Authorization": "Bearer test"},
        ), mock.patch("src.outlook_service.requests.patch") as patch_req, \
                mock.patch.object(self.service, "_get_raw_event", return_value=self.raw):
            patch_req.return_value.status_code = 200
            patch_req.return_value.json.return_value = _graph_event()
            self.service.update_event("evt-1", **kwargs)
        return patch_req.call_args.kwargs["json"]

    def test_change_room_keeps_other_attendees(self):
        body = self._update(room="801")
        self.assertEqual([a["type"] for a in body["attendees"]],
                         ["required", "resource"])
        self.assertEqual(body["attendees"][0]["emailAddress"]["address"],
                         "guest@arraycomm.com")
        self.assertEqual(body["attendees"][1]["emailAddress"]["address"], ROOM_801)
        self.assertEqual(body["location"]["locationEmailAddress"], ROOM_801)
        self.assertEqual(body["location"]["displayName"], room_label(ROOM_801))

    def test_empty_room_clears_room_attendees(self):
        body = self._update(room="")
        self.assertEqual(body["attendees"], [
            {"type": "required", "emailAddress": {"address": "guest@arraycomm.com"}}
        ])
        self.assertNotIn("location", body)

    def test_room_untouched_when_not_provided(self):
        body = self._update(title="新标题")
        self.assertNotIn("attendees", body)
        self.assertNotIn("location", body)

    def test_illegal_room_raises(self):
        with self.assertRaises(ValueError):
            self._update(room="地下一层会议室")


class GetScheduleTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()
        self.day_start = datetime(2026, 9, 15, 0, 0, tzinfo=TZ)
        self.day_end = datetime(2026, 9, 16, 0, 0, tzinfo=TZ)

    def _call(self, addresses, payload):
        with mock.patch(
            "src.outlook_service._headers",
            return_value={"Authorization": "Bearer test"},
        ), mock.patch("src.outlook_service.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"value": payload}
            results = self.service.get_schedule(addresses, self.day_start, self.day_end)
        return results, post

    def test_parses_view_items_and_errors(self):
        results, _ = self._call(["room@x.com", "fallback@x.com", "ghost@x.com"], [
            {"scheduleId": "room@x.com", "availabilityView": "0000200"},
            {"scheduleId": "fallback@x.com", "scheduleItems": [
                {"status": "busy",
                 "start": {"dateTime": "2026-09-15T02:00:00.0000000", "timeZone": "UTC"},
                 "end": {"dateTime": "2026-09-15T03:00:00.0000000", "timeZone": "UTC"}},
            ]},
            {"scheduleId": "ghost@x.com",
             "error": {"message": "Unable to resolve e-mail address", "responseCode": "5009"}},
        ])
        self.assertIsNone(results[0]["error"])
        self.assertEqual(results[0]["busy"], [
            (datetime(2026, 9, 15, 4, 0, tzinfo=TZ),
             datetime(2026, 9, 15, 5, 0, tzinfo=TZ)),
        ])
        self.assertEqual(results[1]["busy"][0][0].astimezone(TZ).hour, 10)
        self.assertIn("Unable to resolve", results[2]["error"])

    def test_chunks_long_address_lists(self):
        addresses = [f"{ROOM_NAME_PREFIX}{n}@{ROOM_EMAIL_DOMAIN}" for n in range(800, 920)]
        _, post = self._call(addresses, [])
        self.assertEqual(post.call_count, 3)
        for call in post.call_args_list:
            self.assertLessEqual(len(call.kwargs["json"]["schedules"]), 50)

    def test_empty_addresses_raises(self):
        with self.assertRaises(ValueError):
            self.service.get_schedule([], self.day_start, self.day_end)

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            self.service.get_schedule(["room@x.com"], self.day_end, self.day_start)


class ScanRoomsTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()
        self.start = datetime(2026, 9, 15, 10, 0, tzinfo=TZ)
        self.end = datetime(2026, 9, 15, 11, 0, tzinfo=TZ)

    def test_filters_unresolvable_and_keeps_only_overlapping_busy(self):
        schedule = [
            {"address": ROOM_801, "error": None, "availability_view": "000020000000",
             "busy": [(datetime(2026, 9, 15, 10, 0, tzinfo=TZ),
                       datetime(2026, 9, 15, 11, 0, tzinfo=TZ))]},
            {"address": f"{ROOM_NAME_PREFIX}802@{ROOM_EMAIL_DOMAIN}",
             "error": "Unable to resolve e-mail address", "busy": [],
             "availability_view": None},
        ]
        with mock.patch.object(self.service, "get_schedule", return_value=schedule):
            rooms = self.service.scan_rooms(801, 850, self.start, self.end)
        self.assertEqual([room["label"] for room in rooms], [room_label(ROOM_801)])
        self.assertEqual(rooms[0]["busy_in_range"], [(self.start, self.end)])

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            self.service.scan_rooms(850, 800, self.start, self.end)

    def test_too_many_numbers_raises(self):
        with self.assertRaises(ValueError):
            self.service.scan_rooms(1, 500, self.start, self.end)


if __name__ == "__main__":
    unittest.main()

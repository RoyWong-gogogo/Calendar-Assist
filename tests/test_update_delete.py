"""update_event / delete_event / get_event 的单元测试（mock 网络，不碰真实日历）。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.ics_service import IcsCalendarService, IcsError
from src.outlook_service import (
    OutlookApiError,
    OutlookCalendarService,
    _to_event_dict,
)
from src.rooms import expand_room

TZ = ZoneInfo(CALENDAR_TIMEZONE)
EVENT_ID = "AAMk-test-id-123"


def _graph_event():
    return {
        "id": EVENT_ID,
        "subject": "原日程",
        "start": {"dateTime": "2026-09-14T09:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "end": {"dateTime": "2026-09-14T10:00:00.0000000", "timeZone": CALENDAR_TIMEZONE},
        "isAllDay": False,
        "location": {"displayName": "老地点"},
        "body": {"contentType": "html", "content": "<p>老备注</p>"},
    }


class GetEventTests(unittest.TestCase):
    def setUp(self):
        # 必须连 _headers 一起 mock：否则会真的去 MSAL 取 token（依赖网络与凭证缓存）
        patcher = mock.patch("src.outlook_service._headers",
                             return_value={"Authorization": "Bearer t"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_get_event_success(self):
        service = OutlookCalendarService()
        with mock.patch("src.outlook_service.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = _graph_event()
            ev = service.get_event(EVENT_ID)
        self.assertIn(EVENT_ID, get.call_args.args[0])
        self.assertEqual(ev["title"], "原日程")
        self.assertEqual(ev["location"], "老地点")

    def test_get_event_404(self):
        service = OutlookCalendarService()
        with mock.patch("src.outlook_service.requests.get") as get:
            get.return_value.status_code = 404
            with self.assertRaises(OutlookApiError) as ctx:
                service.get_event("bad-id")
        self.assertIn("不存在", str(ctx.exception))

    def test_recurring_flags_mapped(self):
        service = OutlookCalendarService()
        data = _graph_event()
        data["seriesMasterId"] = "master-1"
        with mock.patch("src.outlook_service.requests.get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = data
            ev = service.get_event(EVENT_ID)
        self.assertEqual(ev["series_master_id"], "master-1")
        self.assertFalse(ev["is_series_master"])


class UpdateEventTests(unittest.TestCase):
    def setUp(self):
        self.service = OutlookCalendarService()

    def _patch(self, **kwargs):
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.patch") as patch:
            patch.return_value.status_code = 200
            patch.return_value.json.return_value = _graph_event()
            result = self.service.update_event(EVENT_ID, **kwargs)
        return result, patch

    def test_patch_url_and_partial_body(self):
        _, patch = self._patch(title="新标题")
        url = patch.call_args.args[0]
        self.assertIn(f"/me/events/{EVENT_ID}", url)
        body = patch.call_args.kwargs["json"]
        self.assertEqual(body, {"subject": "新标题"})  # 只提交显式提供的字段

    def test_patch_new_times(self):
        _, patch = self._patch(
            start=datetime(2026, 9, 14, 16, tzinfo=TZ),
            end=datetime(2026, 9, 14, 17, tzinfo=TZ),
        )
        body = patch.call_args.kwargs["json"]
        self.assertEqual(body["start"]["dateTime"], "2026-09-14T16:00:00")
        self.assertEqual(body["end"]["dateTime"], "2026-09-14T17:00:00")

    def test_patch_clear_location_with_empty_string(self):
        _, patch = self._patch(location="")
        body = patch.call_args.kwargs["json"]
        self.assertEqual(body["location"], {"displayName": ""})

    def test_empty_title_raises(self):
        with self.assertRaises(ValueError):
            self.service.update_event(EVENT_ID, title="  ")

    def test_invalid_new_range_raises(self):
        with self.assertRaises(ValueError):
            self.service.update_event(
                EVENT_ID,
                start=datetime(2026, 9, 14, 17, tzinfo=TZ),
                end=datetime(2026, 9, 14, 16, tzinfo=TZ),
            )

    def test_no_fields_raises(self):
        with self.assertRaises(ValueError):
            self.service.update_event(EVENT_ID)

    def test_empty_event_id_raises(self):
        with self.assertRaises(ValueError):
            self.service.update_event("", title="x")

    def test_update_404(self):
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.patch") as patch:
            patch.return_value.status_code = 404
            with self.assertRaises(OutlookApiError) as ctx:
                self.service.update_event(EVENT_ID, title="x")
        self.assertIn("不存在", str(ctx.exception))

    def test_update_http_error_details(self):
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.patch") as patch:
            patch.return_value.status_code = 400
            patch.return_value.text = "bad request body"
            with self.assertRaises(OutlookApiError) as ctx:
                self.service.update_event(EVENT_ID, title="x")
        self.assertIn("400", str(ctx.exception))


class UpdateAttendeesTests(unittest.TestCase):
    """邀请 / 移除与会人：只动普通与会人，会议室条目按 --room 语义处理。"""

    def setUp(self):
        self.service = OutlookCalendarService()

    def _update(self, existing=None, raw=None, **kwargs):
        """执行 update_event，返回 (patch 请求的 json body, patch mock, get mock)。"""
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.patch") as patch_req, \
             mock.patch("src.outlook_service.requests.get") as get:
            patch_req.return_value.status_code = 200
            patch_req.return_value.json.return_value = _graph_event()
            if raw is not None:
                get.return_value.status_code = 200
                get.return_value.json.return_value = raw
            self.service.update_event(EVENT_ID, existing_attendees=existing, **kwargs)
        return patch_req.call_args.kwargs["json"], patch_req, get

    def test_add_attendee_keeps_existing_people_and_room(self):
        existing = [
            {"type": "required", "address": "guest@arraycomm.com", "name": "Guest",
             "response": "accepted"},
            {"type": "resource", "address": expand_room("801"),
             "name": "CDConfRoom801", "response": "accepted"},
        ]
        body, _, get = self._update(existing, attendees=["Emma.Zhou@arraycomm.com"])
        get.assert_not_called()  # 复用 get_event 已取回的与会人
        self.assertEqual(body["attendees"], [
            {"type": "required",
             "emailAddress": {"address": "guest@arraycomm.com", "name": "Guest"}},
            {"type": "required",
             "emailAddress": {"address": "Emma.Zhou@arraycomm.com"}},
            {"type": "resource",
             "emailAddress": {"address": expand_room("801"),
                              "name": "CDConfRoom801"}},
        ])
        self.assertNotIn("subject", body)  # 没给字段就不提交

    def test_add_attendee_without_cached_attendees_reads_event(self):
        raw = _graph_event()
        raw["attendees"] = [
            {"type": "required",
             "emailAddress": {"address": "guest@arraycomm.com", "name": "Guest"}},
        ]
        body, _, get = self._update(None, raw=raw, attendees=["new@arraycomm.com"])
        get.assert_called_once()
        self.assertEqual([entry["emailAddress"]["address"] for entry in body["attendees"]],
                         ["guest@arraycomm.com", "new@arraycomm.com"])

    def test_remove_attendee_drops_only_target(self):
        existing = [
            {"type": "required", "address": "guest@arraycomm.com", "name": "Guest"},
            {"type": "required", "address": "keep@arraycomm.com", "name": "Keep"},
        ]
        body, _, _ = self._update(existing, remove_attendees=["GUEST@arraycomm.com"])
        self.assertEqual([entry["emailAddress"]["address"] for entry in body["attendees"]],
                         ["keep@arraycomm.com"])

    def test_duplicate_invite_is_not_added_twice(self):
        existing = [{"type": "required", "address": "emma.zhou@arraycomm.com"}]
        body, _, _ = self._update(existing, attendees=["Emma.Zhou@arraycomm.com"])
        self.assertEqual(len(body["attendees"]), 1)

    def test_room_change_replaces_resource_and_keeps_new_people(self):
        existing = [
            {"type": "resource", "address": expand_room("801"),
             "name": "CDConfRoom801", "response": "accepted"},
        ]
        body, _, _ = self._update(existing, room="803",
                                  attendees=["new@arraycomm.com"])
        self.assertEqual(body["attendees"], [
            {"type": "required", "emailAddress": {"address": "new@arraycomm.com"}},
            {"type": "resource",
             "emailAddress": {"address": expand_room("803"),
                              "name": "CDConfRoom803"}},
        ])
        self.assertEqual(body["location"]["displayName"], "CDConfRoom803")

    def test_invalid_attendee_email_raises_before_reading_event(self):
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.get") as get:
            with self.assertRaises(ValueError):
                self.service.update_event(EVENT_ID, attendees=["not-an-email"])
        get.assert_not_called()


class DeleteEventTests(unittest.TestCase):
    def test_delete_success_204(self):
        service = OutlookCalendarService()
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.delete") as delete:
            delete.return_value.status_code = 204
            service.delete_event(EVENT_ID)  # 不抛异常即成功
        self.assertIn(f"/me/events/{EVENT_ID}", delete.call_args.args[0])

    def test_delete_404(self):
        service = OutlookCalendarService()
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.delete") as delete:
            delete.return_value.status_code = 404
            with self.assertRaises(OutlookApiError) as ctx:
                service.delete_event("gone-id")
        self.assertIn("不存在", str(ctx.exception))

    def test_delete_other_http_error(self):
        service = OutlookCalendarService()
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.delete") as delete:
            delete.return_value.status_code = 403
            delete.return_value.text = "forbidden"
            with self.assertRaises(OutlookApiError) as ctx:
                service.delete_event(EVENT_ID)
        self.assertIn("403", str(ctx.exception))

    def test_empty_event_id_raises(self):
        with self.assertRaises(ValueError):
            OutlookCalendarService().delete_event("")


class ReadOnlyBackendsRejectWrites(unittest.TestCase):
    def test_ics_rejects_get_update_delete(self):
        service = IcsCalendarService()
        for call in (lambda: service.get_event("x"),
                     lambda: service.update_event("x", title="y"),
                     lambda: service.delete_event("x")):
            with self.assertRaises(IcsError):
                call()


class AttendeeMappingTests(unittest.TestCase):
    def test_attendees_and_room_responses_exposed(self):
        data = _graph_event()
        data["attendees"] = [
            {"type": "required",
             "emailAddress": {"address": "guest@arraycomm.com", "name": "Guest"},
             "status": {"response": "none", "time": "0001-01-01T00:00:00Z"}},
            {"type": "resource",
             "emailAddress": {"address": expand_room("801"), "name": "CDConfRoom801"},
             "status": {"response": "accepted", "time": "2026-09-14T09:00:00Z"}},
        ]
        ev = _to_event_dict(data)
        self.assertEqual(ev["rooms"], [expand_room("801")])
        self.assertEqual(ev["room_responses"][0]["response"], "accepted")
        self.assertEqual([a["type"] for a in ev["attendees"]], ["required", "resource"])
        self.assertEqual(ev["attendees"][0]["response"], "none")

    def test_no_attendees_key_yields_empty_lists(self):
        ev = _to_event_dict(_graph_event())
        self.assertEqual(ev["rooms"], [])
        self.assertEqual(ev["room_responses"], [])
        self.assertEqual(ev["attendees"], [])

    def test_update_room_reuses_provided_attendees(self):
        service = OutlookCalendarService()
        provided = [
            {"type": "required", "address": "guest@arraycomm.com", "name": "Guest",
             "response": "none"},
            {"type": "resource", "address": expand_room("808"), "name": "CDConfRoom808",
             "response": "accepted"},
        ]
        with mock.patch("src.outlook_service._headers",
                        return_value={"Authorization": "Bearer t"}), \
             mock.patch("src.outlook_service.requests.patch") as patch_req, \
             mock.patch("src.outlook_service.requests.get") as get:
            patch_req.return_value.status_code = 200
            patch_req.return_value.json.return_value = _graph_event()
            service.update_event(EVENT_ID, room="801", existing_attendees=provided)
        get.assert_not_called()  # 复用了 get_event 已取回的与会人，不再多发一次读取
        body = patch_req.call_args.kwargs["json"]
        self.assertEqual(body["attendees"], [
            {"type": "required",
             "emailAddress": {"address": "guest@arraycomm.com", "name": "Guest"}},
            {"type": "resource",
             "emailAddress": {"address": expand_room("801"), "name": "CDConfRoom801"}},
        ])


if __name__ == "__main__":
    unittest.main()

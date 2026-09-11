"""Outlook Calendar（Microsoft Graph API）封装。

与 src/calendar_service.py（Google 实现）保持一致的 list_events 返回结构，
由 src/service_factory.py 按 CALENDAR_PROVIDER 选择实现。
OAuth 细节独立在 src/outlook_auth.py。
Graph 端点由 OUTLOOK_CLOUD 控制（china 默认 / global），见 src/config.py。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from src.config import (
    CALENDAR_TIMEZONE,
    GRAPH_BASE_URL,
    ROOM_EMAIL_DOMAIN,
    ROOM_NAME_PREFIX,
)
from src.datetime_utils import ensure_aware, get_tz, to_iso
from src.free_time import find_free_slots
from src.outlook_auth import get_access_token
from src.rooms import expand_room, room_label

GRAPH_BASE = GRAPH_BASE_URL
TIMEOUT_SECONDS = 30
# 一次扫描会议室编号的上限（内部按 50 个一批调用 getSchedule）
MAX_ROOM_SCAN = 200
_SCHEDULE_CHUNK = 50

_SELECT_FIELDS = "id,subject,start,end,isAllDay,location,body,seriesMasterId,attendees"
_GET_FIELDS = "id,subject,start,end,isAllDay,location,body,seriesMasterId,recurrence,attendees"
_FRACTION_RE = re.compile(r"\.\d+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class OutlookApiError(RuntimeError):
    """Microsoft Graph API 调用失败。"""


class OutlookCalendarService:
    """封装对当前账号默认（主）日历的操作。"""

    def __init__(self):
        # 与 Google 实现保持一致的属性，便于脚本统一显示
        self.calendar_id = "primary"

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        """查询 [start, end) 时间段内的所有事件。

        返回字段与 Google 实现一致：
        id / title / start / end / all_day / location / description。
        """
        start = ensure_aware(start)
        end = ensure_aware(end)
        if end <= start:
            raise ValueError(
                f"查询结束时间必须晚于开始时间: {to_iso(start)} -> {to_iso(end)}"
            )

        tz = get_tz()
        url = f"{GRAPH_BASE}/me/calendarview"
        params = {
            "startDateTime": to_iso(start.astimezone(tz)),
            "endDateTime": to_iso(end.astimezone(tz)),
            "$select": _SELECT_FIELDS,
        }
        raw_events: list[dict] = []
        try:
            while url:
                response = requests.get(
                    url, params=params, headers=_headers(), timeout=TIMEOUT_SECONDS
                )
                if response.status_code != 200:
                    raise OutlookApiError(
                        f"调用 Microsoft Graph 查询日程失败"
                        f"（HTTP {response.status_code}, 范围 {to_iso(start)} ~ {to_iso(end)}）: "
                        f"{response.text[:500]}"
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise OutlookApiError(
                        f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
                    ) from exc
                raw_events.extend(data.get("value", []))
                url = data.get("@odata.nextLink")
                params = None  # nextLink 已自带全部查询参数
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 失败（网络错误）: {exc}"
            ) from exc

        events = [_to_event_dict(item) for item in raw_events]
        # calendarView 通常按开始时间排序，这里再排一次保证输出顺序稳定
        events.sort(
            key=lambda ev: ev["start"] or datetime.min.replace(tzinfo=timezone.utc)
        )
        return events

    def create_event(self, title: str, start: datetime, end: datetime,
                     location: str | None = None,
                     description: str | None = None,
                     room: str | None = None) -> dict:
        """在默认（主）日历上创建日程，返回与 list_events 一致的事件字典。

        title / start / end 必填；location / description / room 可选。
        room（编号 / 名称 / 邮箱）会作为 resource 与会人加入邀请，Exchange 据此
        真正占用会议室；未显式给 location 时用它作为地点显示名。会议室是否可用
        由调用方先用 get_schedule 检查（脚本层负责，见 scripts/create_event.py）。
        """
        if not title or not title.strip():
            raise ValueError("日程标题不能为空")
        start = ensure_aware(start)
        end = ensure_aware(end)
        if end <= start:
            raise ValueError(
                f"结束时间必须晚于开始时间: {to_iso(start)} -> {to_iso(end)}"
            )

        room_address = expand_room(room) if room else None

        tz = get_tz()
        body = {
            "subject": title.strip(),
            "start": _graph_datetime(start, tz),
            "end": _graph_datetime(end, tz),
        }
        if room_address:
            body["location"] = {
                "displayName": location or room_label(room_address),
                "locationEmailAddress": room_address,
            }
            body["attendees"] = [_room_attendee(room_address)]
        elif location:
            body["location"] = {"displayName": location}
        if description:
            body["body"] = {"contentType": "text", "content": description}

        try:
            response = requests.post(
                f"{GRAPH_BASE}/me/events",
                json=body,
                headers=_headers(),
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 创建日程失败（网络错误）: {exc}"
            ) from exc
        if response.status_code != 201:
            raise OutlookApiError(
                f"创建日程失败（HTTP {response.status_code}）: {response.text[:500]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise OutlookApiError(
                f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
            ) from exc
        return _to_event_dict(data)

    def get_event(self, event_id: str) -> dict:
        """按 id 读取单个事件（修改 / 删除前用于确认目标）。"""
        if not event_id:
            raise ValueError("event_id 不能为空")
        try:
            response = requests.get(
                f"{GRAPH_BASE}/me/events/{quote(event_id, safe='')}",
                params={"$select": _GET_FIELDS},
                headers=_headers(),
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 读取日程失败（网络错误）: {exc}"
            ) from exc
        if response.status_code == 404:
            raise OutlookApiError(f"事件不存在（id 无效或已被删除）: {event_id[:50]}")
        if response.status_code != 200:
            raise OutlookApiError(
                f"读取日程失败（HTTP {response.status_code}）: {response.text[:500]}"
            )
        try:
            return _to_event_dict(response.json())
        except ValueError as exc:
            raise OutlookApiError(
                f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
 ) from exc

    def _get_raw_event(self, event_id: str) -> dict:
        """读取 Graph 原始事件对象（修改会议室时需要保留其他与会人）。"""
        try:
            response = requests.get(
                f"{GRAPH_BASE}/me/events/{quote(event_id, safe='')}",
                params={"$select": "id,attendees"},
                headers=_headers(),
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 读取日程失败（网络错误）: {exc}"
            ) from exc
        if response.status_code != 200:
            raise OutlookApiError(
                f"读取日程失败（HTTP {response.status_code}）: {response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise OutlookApiError(
                f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
            ) from exc

    def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        location: str | None = None,
        description: str | None = None,
        room: str | None = None,
    ) -> dict:
        """按 id 修改事件，仅提交显式提供的字段，返回更新后的事件字典。

        - None（默认）表示该字段保持不变；location / description 传空字符串表示清空
        - room=None 表示会议室不变；room="" 表示取消会议室；其他值表示改为该会议室
          （会议室以 resource 与会人形式存在；改会议室时会先读取原事件，
          保留其他非 resource 与会人，避免把他们一起冲掉）
        - 同时提供 start/end 时校验相对关系；只改其一时与旧值的组合
          由调用方（脚本层先 get_event）保证有效
        - 重复日程：对实例 id 操作仅影响该场，对系列母事件 id 操作影响
          整个系列；语义不明确时调用方（Codex）必须先询问用户
        """
        if not event_id:
            raise ValueError("event_id 不能为空")

        start_dt = ensure_aware(start) if start is not None else None
        end_dt = ensure_aware(end) if end is not None else None
        if start_dt is not None and end_dt is not None and end_dt <= start_dt:
            raise ValueError(
                f"结束时间必须晚于开始时间: {to_iso(start_dt)} -> {to_iso(end_dt)}"
            )

        patch: dict = {}
        if title is not None:
            if not title.strip():
                raise ValueError("日程标题不能为空")
            patch["subject"] = title.strip()
        if start_dt is not None:
            patch["start"] = _graph_datetime(start_dt, get_tz())
        if end_dt is not None:
            patch["end"] = _graph_datetime(end_dt, get_tz())
        room_address = None
        if room is not None:
            room_address = expand_room(room) if room.strip() else None
            attendees = [
                attendee
                for attendee in (self._get_raw_event(event_id).get("attendees") or [])
                if (attendee.get("type") or "").lower() != "resource"
            ]
            if room_address:
                attendees.append(_room_attendee(room_address))
            patch["attendees"] = attendees
        if location is not None:
            entry = {"displayName": location}
            if room_address and location:
                entry["locationEmailAddress"] = room_address
            patch["location"] = entry
        elif room_address:
            patch["location"] = {
                "displayName": room_label(room_address),
                "locationEmailAddress": room_address,
            }
        if description is not None:
            patch["body"] = {"contentType": "text", "content": description}
        if not patch:
            raise ValueError(
                "至少提供一项要修改的字段"
                "（title/start/end/location/description/room）"
            )

        try:
            response = requests.patch(
                f"{GRAPH_BASE}/me/events/{quote(event_id, safe='')}",
                json=patch,
                headers=_headers(),
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 修改日程失败（网络错误）: {exc}"
            ) from exc
        if response.status_code == 404:
            raise OutlookApiError(f"事件不存在（id 无效或已被删除）: {event_id[:50]}")
        if response.status_code != 200:
            raise OutlookApiError(
                f"修改日程失败（HTTP {response.status_code}）: {response.text[:500]}"
            )
        try:
            return _to_event_dict(response.json())
        except ValueError as exc:
            raise OutlookApiError(
                f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
            ) from exc

    def delete_event(self, event_id: str) -> None:
        """按 id 删除事件。调用方必须先 get_event 展示目标并经用户确认。"""
        if not event_id:
            raise ValueError("event_id 不能为空")
        try:
            response = requests.delete(
                f"{GRAPH_BASE}/me/events/{quote(event_id, safe='')}",
                headers=_headers(),
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OutlookApiError(
                f"请求 Microsoft Graph 删除日程失败（网络错误）: {exc}"
            ) from exc
        if response.status_code == 404:
            raise OutlookApiError(f"事件不存在（id 无效或已被删除）: {event_id[:50]}")
        if response.status_code != 204:
            raise OutlookApiError(
                f"删除日程失败（HTTP {response.status_code}）: {response.text[:500]}"
            )

    def get_schedule(self, addresses: list[str], start: datetime, end: datetime,
                     interval_minutes: int = 60) -> list[dict]:
        """查询一组邮箱（含会议室）在 [start, end) 的忙闲，顺序与入参一致。

        使用 POST /me/calendar/getSchedule（委托权限 Calendars.ReadWrite 即可，
        中国区实测可用），每项返回：
        - address：请求的邮箱地址
        - error：邮箱无法解析时的错误消息（正常为 None，例如 5009 表示地址不存在）
        - busy：[(aware start, aware end), ...] 忙碌时段（空闲不计入）
        - availability_view：Graph 返回的忙闲字符串（每位 interval_minutes）
        """
        if not addresses:
            raise ValueError("addresses 不能为空")
        start = ensure_aware(start)
        end = ensure_aware(end)
        if end <= start:
            raise ValueError(
                f"查询结束时间必须晚于开始时间: {to_iso(start)} -> {to_iso(end)}"
            )
        if interval_minutes <= 0:
            raise ValueError(f"interval_minutes 必须为正整数: {interval_minutes}")

        tz = get_tz()
        results: list[dict] = []
        for index in range(0, len(addresses), _SCHEDULE_CHUNK):
            chunk = list(addresses[index:index + _SCHEDULE_CHUNK])
            body = {
                "schedules": chunk,
                "startTime": _graph_datetime(start, tz),
                "endTime": _graph_datetime(end, tz),
                "availabilityViewInterval": interval_minutes,
            }
            try:
                response = requests.post(
                    f"{GRAPH_BASE}/me/calendar/getSchedule",
                    json=body,
                    headers=_headers(),
                    timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                raise OutlookApiError(
                    f"请求 Microsoft Graph 查询忙闲失败（网络错误）: {exc}"
                ) from exc
            if response.status_code != 200:
                raise OutlookApiError(
                    f"查询忙闲失败（HTTP {response.status_code}）: {response.text[:500]}"
                )
            try:
                data = response.json()
            except ValueError as exc:
                raise OutlookApiError(
                    f"Microsoft Graph 返回了无法解析的响应: {response.text[:200]}"
                ) from exc

            for item in data.get("value", []):
                view = item.get("availabilityView")
                busy = (
                    _busy_from_view(view, start, interval_minutes)
                    if view
                    else _busy_from_items(item.get("scheduleItems"))
                )
                results.append({
                    "address": item.get("scheduleId") or "",
                    "error": (item.get("error") or {}).get("message"),
                    "busy": busy,
                    "availability_view": view,
                })
        return results

    def scan_rooms(self, first: int, last: int, start: datetime, end: datetime,
                   prefix: str | None = None, domain: str | None = None,
                   interval_minutes: int = 60) -> list[dict]:
        """按编号区间扫描会议室邮箱，返回真实存在的会议室及其在 [start, end) 的占用。

        中国区 Graph 没有可用的会议室清单接口（/me/findRooms 需要额外权限、
        /places 未在中国区开放），因此按「前缀 + 编号 @ 域名」命名规律枚举，
        再用 getSchedule 确认哪些邮箱真实存在。返回：
        {"address", "label", "busy_in_range": [(start, end), ...]}
        仅包含可解析的地址；无法解析的编号视为不存在。
        """
        if last < first:
            raise ValueError(f"会议室编号区间无效: {first} > {last}")
        if last - first + 1 > MAX_ROOM_SCAN:
            raise ValueError(
                f"一次最多扫描 {MAX_ROOM_SCAN} 个编号（当前 {last - first + 1} 个）"
            )
        room_prefix = prefix or ROOM_NAME_PREFIX
        room_domain = domain or ROOM_EMAIL_DOMAIN
        addresses = [
            f"{room_prefix}{number}@{room_domain}" for number in range(first, last + 1)
        ]

        rooms: list[dict] = []
        for info in self.get_schedule(addresses, start, end, interval_minutes):
            if info["error"] or not info["address"]:
                continue
            rooms.append({
                "address": info["address"],
                "label": room_label(info["address"]),
                "busy_in_range": [
                    (slot_start, slot_end)
                    for slot_start, slot_end in info["busy"]
                    if slot_start < end and start < slot_end
                ],
            })
        return rooms

    def find_free_time(self, start: datetime, end: datetime,
                       duration_minutes: int) -> list[tuple[datetime, datetime]]:
        """在 [start, end) 内返回所有 ≥ duration_minutes 的空闲区间。

        v0.1 简化：日历上的所有事件都视为忙碌
        （不区分 Graph 的 showAs 空闲状态标记）。
        """
        busy = self.list_events(start, end)
        return find_free_slots(busy, start, end, timedelta(minutes=duration_minutes))


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        # 让 Graph 把时间换算成配置时区返回；即使服务端忽略此偏好，
        # parse_graph_datetime 也能正确处理带偏移的返回值
        "Prefer": f'outlook.timezone="{CALENDAR_TIMEZONE}"',
    }


def _graph_datetime(dt: datetime, tz) -> dict:
    """把 aware datetime 格式化为 Graph 需要的 {dateTime, timeZone} 结构。"""
    return {
        "dateTime": dt.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%S"),
        "timeZone": CALENDAR_TIMEZONE,
    }


def _room_attendee(address: str) -> dict:
    """会议室在 Graph 事件里的写法：resource 类型与会人（Exchange 据此占用会议室）。"""
    return {
        "type": "resource",
        "emailAddress": {"address": address, "name": room_label(address)},
    }


def _resource_addresses(attendees) -> list[str]:
    """取出事件中 resource 类型（会议室 / 设备）与会人的邮箱地址。"""
    result: list[str] = []
    for attendee in attendees or []:
        if (attendee.get("type") or "").lower() != "resource":
            continue
        address = ((attendee.get("emailAddress") or {}).get("address") or "").strip()
        if address:
            result.append(address)
    return result


def _busy_from_view(view: str, start: datetime,
                    interval_minutes: int) -> list[tuple[datetime, datetime]]:
    """把 getSchedule 的 availabilityView 字符串转成忙碌区间。

    Graph 每位代表一个 interval_minutes：0=空闲，1=暂定，2=忙碌，3=离开，
    4=其他。非 0 一律视为忙碌（与 v0.1「所有事件都算忙碌」的简化一致），
    相邻的忙碌位合并为连续区间。
    """
    tz = get_tz()
    base = start.astimezone(tz)
    slots: list[tuple[datetime, datetime]] = []
    for index, char in enumerate(view or ""):
        if char in ("0", ""):
            continue
        slot_start = base + timedelta(minutes=interval_minutes * index)
        slot_end = slot_start + timedelta(minutes=interval_minutes)
        if slots and slots[-1][1] == slot_start:
            slots[-1] = (slots[-1][0], slot_end)
        else:
            slots.append((slot_start, slot_end))
    return slots


def _busy_from_items(items) -> list[tuple[datetime, datetime]]:
    """从 getSchedule 的 scheduleItems 解析忙碌区间（status=free 的忽略）。

    availabilityView 缺失时（对方邮箱不返回明文忙闲）用这里兜底。
    """
    busy: list[tuple[datetime, datetime]] = []
    for item in items or []:
        if (item.get("status") or "").lower() == "free":
            continue
        slot_start = parse_graph_datetime(item.get("start"))
        slot_end = parse_graph_datetime(item.get("end"))
        if slot_start and slot_end and slot_end > slot_start:
            busy.append((slot_start, slot_end))
    busy.sort(key=lambda pair: pair[0])
    return busy


def _to_event_dict(item: dict) -> dict:
    """把 Graph 返回的事件对象转成与 Google 实现一致的简洁字典。"""
    location = (item.get("location") or {}).get("displayName") or None
    body = (item.get("body") or {}).get("content") or None
    return {
        "id": item.get("id", ""),
        "title": item.get("subject") or "(无标题)",
        "start": parse_graph_datetime(item.get("start")),
        "end": parse_graph_datetime(item.get("end")),
        "all_day": bool(item.get("isAllDay", False)),
        "location": location,
        "description": _strip_html(body) if body else None,
        "rooms": _resource_addresses(item.get("attendees")),
        "series_master_id": item.get("seriesMasterId"),
        "is_series_master": bool(item.get("recurrence")),
    }


def _strip_html(text: str) -> str | None:
    """去掉 Outlook 正文里的 HTML 标签与实体，便于在终端显示。

    无实际内容时（如空正文只剩 &nbsp;）返回 None。
    """
    plain = html.unescape(_HTML_TAG_RE.sub(" ", text))
    stripped = re.sub(r"\s+", " ", plain).strip()
    return stripped or None


def parse_graph_datetime(value: dict | None) -> datetime | None:
    """解析 Graph 事件的 start/end 字段。

    Graph 返回形如 {"dateTime": "2026-09-10T09:00:00.0000000", "timeZone": "..."}：
    - 带时区偏移（或以 Z 结尾）的 dateTime 直接解析为 aware datetime
    - naive 值优先用 timeZone 字段（IANA 名称）解释；Windows 时区名或缺失时
      退回配置时区（配合 Prefer 头，naive 值本就应是配置时区）
    """
    if not isinstance(value, dict):
        return None
    raw = value.get("dateTime")
    if not raw:
        return None

    # Graph 的秒位小数可能多达 7 位，标准库解析前先截掉（保留 Z/偏移后缀）
    raw = _FRACTION_RE.sub("", raw, count=1)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise OutlookApiError(f"无法解析 Graph 返回的时间: {value!r}") from exc

    if parsed.tzinfo is not None:
        return parsed
    tz_name = (value.get("timeZone") or "").strip()
    try:
        return parsed.replace(tzinfo=ZoneInfo(tz_name))
    except Exception:
        return parsed.replace(tzinfo=get_tz())

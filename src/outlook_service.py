"""Outlook Calendar（Microsoft Graph API）封装。

与 src/calendar_service.py（Google 实现）保持一致的 list_events 返回结构，
由 src/service_factory.py 按 CALENDAR_PROVIDER 选择实现。
OAuth 细节独立在 src/outlook_auth.py。
Graph 端点由 OUTLOOK_CLOUD 控制（china 默认 / global），见 src/config.py。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from src.config import CALENDAR_TIMEZONE, GRAPH_BASE_URL
from src.datetime_utils import ensure_aware, get_tz, to_iso
from src.outlook_auth import get_access_token

GRAPH_BASE = GRAPH_BASE_URL
TIMEOUT_SECONDS = 30

_SELECT_FIELDS = "id,subject,start,end,isAllDay,location,body"
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


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        # 让 Graph 把时间换算成配置时区返回；即使服务端忽略此偏好，
        # parse_graph_datetime 也能正确处理带偏移的返回值
        "Prefer": f'outlook.timezone="{CALENDAR_TIMEZONE}"',
    }


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
    }


def _strip_html(text: str) -> str:
    """去掉 Outlook 正文里的 HTML 标签，便于在终端显示。"""
    plain = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", plain).strip()


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

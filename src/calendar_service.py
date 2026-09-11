"""Google Calendar API 的薄封装。

当前不可用（Google 登录无法完成，仅保留代码）。list_events 完整实现；
写入操作（create/update/delete）抛出 NotImplementedError；
find_free_time 基于查询结果计算。
OAuth 细节独立在 src/google_auth.py。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import GOOGLE_CALENDAR_ID
from src.datetime_utils import ensure_aware, get_tz, to_iso
from src.free_time import find_free_slots
from src.google_auth import get_credentials


class CalendarApiError(RuntimeError):
    """Google Calendar API 调用失败。"""


class CalendarService:
    """封装对单个 Google 日历的操作。"""

    def __init__(self, calendar_id: str | None = None):
        self.calendar_id = calendar_id or GOOGLE_CALENDAR_ID
        # 构造时就会完成 OAuth（必要时自动刷新 token 或发起授权）
        self._service = build("calendar", "v3", credentials=get_credentials())

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        """查询 [start, end) 时间段内的所有事件。

        返回字段：id / title / start / end / all_day / location / description。
        start、end 为 timezone-aware datetime；全天事件按配置时区的 00:00 解释。
        """
        start = ensure_aware(start)
        end = ensure_aware(end)
        if end <= start:
            raise ValueError(
                f"查询结束时间必须晚于开始时间: {to_iso(start)} -> {to_iso(end)}"
            )

        items: list[dict] = []
        page_token = None
        try:
            while True:
                response = (
                    self._service.events()
                    .list(
                        calendarId=self.calendar_id,
                        timeMin=to_iso(start),
                        timeMax=to_iso(end),
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=2500,
                        pageToken=page_token,
                    )
                    .execute()
                )
                items.extend(response.get("items", []))
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            raise CalendarApiError(
                f"调用 Google Calendar API 查询事件失败"
                f"（calendarId={self.calendar_id}, 范围 {to_iso(start)} ~ {to_iso(end)}）: {exc}"
            ) from exc

        return [_to_event_dict(item) for item in items]

    def create_event(self, *args, **kwargs) -> dict:
        """Google 后端当前不可用，不支持创建日程。"""
        raise NotImplementedError(
            "Google 后端当前不可用（Google 登录未打通），create_event 未实现。"
            "当前主后端为 Outlook（CALENDAR_PROVIDER=outlook）。"
        )

    def find_free_time(self, start: datetime, end: datetime,
                       duration_minutes: int) -> list[tuple[datetime, datetime]]:
        """在 [start, end) 内返回所有 ≥ duration_minutes 的空闲区间。"""
        busy = self.list_events(start, end)
        return find_free_slots(busy, start, end, timedelta(minutes=duration_minutes))

    def get_event(self, *args, **kwargs) -> dict:
        """Google 后端当前不可用。"""
        raise NotImplementedError(
            "Google 后端当前不可用（Google 登录未打通），get_event 未实现。"
            "当前主后端为 Outlook（CALENDAR_PROVIDER=outlook）。"
        )

    def update_event(self, *args, **kwargs) -> dict:
        """Google 后端当前不可用。"""
        raise NotImplementedError(
            "Google 后端当前不可用（Google 登录未打通），update_event 未实现。"
            "当前主后端为 Outlook（CALENDAR_PROVIDER=outlook）。"
        )

    def delete_event(self, *args, **kwargs) -> None:
        """Google 后端当前不可用。"""
        raise NotImplementedError(
            "Google 后端当前不可用（Google 登录未打通），delete_event 未实现。"
            "当前主后端为 Outlook（CALENDAR_PROVIDER=outlook）。"
        )


def _to_event_dict(item: dict) -> dict:
    """把 Google API 返回的事件对象转成简洁字典。"""
    start_raw = item.get("start") or {}
    return {
        "id": item.get("id", ""),
        "title": item.get("summary", "(无标题)"),
        "start": _parse_google_time(start_raw),
        "end": _parse_google_time(item.get("end")),
        "all_day": "date" in start_raw,
        "location": item.get("location"),
        "description": item.get("description"),
    }


def _parse_google_time(value: dict | None) -> datetime | None:
    """解析 Google 事件的 start/end 字段。

    普通事件为 {"dateTime": "..."}；全天事件为 {"date": "YYYY-MM-DD"}。
    """
    if not isinstance(value, dict):
        return None
    if "dateTime" in value:
        return datetime.fromisoformat(value["dateTime"])
    if "date" in value:
        # 全天事件边界，按配置时区的当天 00:00 解释
        return datetime.combine(
            date.fromisoformat(value["date"]), time.min, tzinfo=get_tz()
        )
    return None

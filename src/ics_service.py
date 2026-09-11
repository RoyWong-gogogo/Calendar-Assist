"""ICS 订阅链接日历后端（只读）。

数据源是 Outlook 网页版「设置 → 日历 → 共享日历 → 发布日历」生成的
ICS 订阅链接：无需 OAuth、无需应用注册、无需任何额外账号。

限制：
- 只读：不支持创建 / 修改 / 删除日程。
- 内容是发布快照，不是实时数据，通常有分钟级以上的延迟。
- ICS 链接本身是机密（任何拿到链接的人都能查看日历），只应保存在 .env。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import recurring_ical_events as rie
import requests
from icalendar import Calendar

from src.config import ICS_URL
from src.datetime_utils import ensure_aware, get_tz, to_iso

TIMEOUT_SECONDS = 30


class IcsError(RuntimeError):
    """ICS 后端配置或调用出错。"""


class IcsCalendarService:
    """通过发布的 ICS 订阅链接读取日历（只读）。"""

    def __init__(self):
        # 与其他后端保持一致的属性，便于脚本统一显示
        self.calendar_id = "published-ics"

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        """查询 [start, end) 时间段内的所有事件。

        返回字段与其他后端一致：
        id / title / start / end / all_day / location / description。
        """
        start = ensure_aware(start)
        end = ensure_aware(end)
        if end <= start:
            raise ValueError(
                f"查询结束时间必须晚于开始时间: {to_iso(start)} -> {to_iso(end)}"
            )
        if not ICS_URL:
            raise IcsError(
                "未配置 ICS_URL。\n"
                "请先在 Outlook 网页版发布日历，再把 ICS 链接填入 .env"
                "（详见 README.md 的「ICS 订阅」一节）:\n"
                "  1. 打开 https://partner.outlook.cn/calendar/options/calendar/SharedCalendars\n"
                "     （或 Outlook 网页版 → 设置 → 日历 → 共享日历）\n"
                "  2. 「发布日历 (Publish a calendar)」→ 选择主日历 → Publish\n"
                "  3. 复制 ICS 链接（用于订阅的那个，不是 HTML 链接）\n"
                "  4. 粘贴到项目根目录 .env 的 ICS_URL= 后面"
            )

        ics_text = self._fetch()
        return self._parse(ics_text, start, end)

    def _fetch(self) -> str:
        try:
            response = requests.get(
                ICS_URL,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "calendar-agent/0.1"},
            )
        except requests.RequestException as exc:
            raise IcsError(f"请求 ICS 订阅失败（网络错误）: {exc}") from exc
        if response.status_code != 200:
            raise IcsError(
                f"拉取 ICS 订阅失败（HTTP {response.status_code}）: {response.text[:300]}"
            )
        return response.text

    def _parse(self, ics_text: str, start: datetime, end: datetime) -> list[dict]:
        try:
            calendar = Calendar.from_ical(ics_text)
        except ValueError as exc:
            raise IcsError(f"ICS 内容无法解析: {exc}") from exc
        try:
            # 自动展开重复日程（RRULE）并截取查询窗口
            occurrences = rie.of(calendar).between(start, end)
        except Exception as exc:
            raise IcsError(f"展开 ICS 日程时出错: {exc}") from exc

        events = [_to_event_dict(component) for component in occurrences]
        events.sort(
            key=lambda ev: ev["start"] or datetime.min.replace(tzinfo=timezone.utc)
        )
        return events


def _to_event_dict(component) -> dict:
    """把 ICS VEVENT 组件转成与其他后端一致的简洁字典。"""
    start, all_day = _component_dt(component.get("DTSTART"))

    end = None
    if start is not None:
        end_prop = component.get("DTEND")
        if end_prop is not None:
            end, _ = _component_dt(end_prop)
        else:
            duration = component.get("DURATION")
            if duration is not None:
                end = start + duration.dt
            else:
                # 全天事件无 DTEND 时按 RFC 5545 视为 1 天；普通事件视为零时长
                end = start + timedelta(days=1) if all_day else start

    return {
        "id": str(component.get("UID") or ""),
        "title": _text(component, "SUMMARY") or "(无标题)",
        "start": start,
        "end": end,
        "all_day": all_day,
        "location": _text(component, "LOCATION"),
        "description": _text(component, "DESCRIPTION"),
    }


def _component_dt(prop) -> tuple[datetime | None, bool]:
    """解析 DTSTART/DTEND 属性，返回 (aware datetime, 是否全天)。

    - DATE 值（全天）按配置时区的当天 00:00 解释
    - 带时区（Z 或 TZID）的值直接使用
    - 无时区的浮动值按配置时区解释
    """
    if prop is None:
        return None, False
    value = prop.dt
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=get_tz()), False
        return value, False
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=get_tz()), True
    return None, False


def _text(component, name: str) -> str | None:
    value = component.get(name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None

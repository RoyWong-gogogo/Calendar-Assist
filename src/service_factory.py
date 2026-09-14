"""按 CALENDAR_PROVIDER 返回日历服务实现。

默认 outlook（中国区 Microsoft Graph，端点由 OUTLOOK_CLOUD 控制）；
ics（只读订阅后备）与 google（过渡期保留）为备选后端。
"""

from __future__ import annotations

from src.config import CALENDAR_PROVIDER


def get_calendar_service_class():
    """返回当前配置对应的日历服务类。"""
    provider = (CALENDAR_PROVIDER or "").strip().lower()
    if provider == "ics":
        from src.ics_service import IcsCalendarService

        return IcsCalendarService
    if provider == "outlook":
        from src.outlook_service import OutlookCalendarService

        return OutlookCalendarService
    if provider == "google":
        from src.calendar_service import CalendarService

        return CalendarService
    raise ValueError(
        f"未知的 CALENDAR_PROVIDER={CALENDAR_PROVIDER!r}，当前支持: outlook / ics / google"
    )

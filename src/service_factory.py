"""按 CALENDAR_PROVIDER 返回日历服务实现（过渡期 Google / Outlook 并存）。

Outlook 验证通过后，将删除 Google 实现并简化本模块。
"""

from __future__ import annotations

from src.config import CALENDAR_PROVIDER


def get_calendar_service_class():
    """返回当前配置对应的日历服务类。"""
    provider = (CALENDAR_PROVIDER or "").strip().lower()
    if provider == "outlook":
        from src.outlook_service import OutlookCalendarService

        return OutlookCalendarService
    if provider == "google":
        from src.calendar_service import CalendarService

        return CalendarService
    raise ValueError(
        f"未知的 CALENDAR_PROVIDER={CALENDAR_PROVIDER!r}，当前支持: outlook / google"
    )

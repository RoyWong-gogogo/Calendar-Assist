"""timezone-aware 的日期时间工具。

规则：
- 所有参与 Google Calendar 操作的 datetime 必须是 timezone-aware 的。
- naive datetime 一律按配置时区（CALENDAR_TIMEZONE）解释。
- 内部时间统一使用 ISO 8601 表示。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.config import CALENDAR_TIMEZONE


def get_tz() -> ZoneInfo:
    """返回配置的日历时区。"""
    try:
        return ZoneInfo(CALENDAR_TIMEZONE)
    except Exception as exc:
        raise ValueError(
            f"无效的时区配置 CALENDAR_TIMEZONE={CALENDAR_TIMEZONE!r}: {exc}"
        ) from exc


def now() -> datetime:
    """当前时刻（timezone-aware，配置时区）。"""
    return datetime.now(get_tz())


def ensure_aware(dt: datetime) -> datetime:
    """确保 datetime 是 timezone-aware 的；naive 值按配置时区解释。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=get_tz())
    return dt


def parse_iso(value: str) -> datetime:
    """解析 ISO 8601 字符串为 timezone-aware datetime。"""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"无法解析为 ISO 8601 时间: {value!r}") from exc
    return ensure_aware(dt)


def to_iso(dt: datetime) -> str:
    """格式化为 ISO 8601 字符串（timezone-aware）。"""
    return ensure_aware(dt).isoformat()


def resolve_day(value: str | date | datetime | None = None) -> date:
    """把 None/today/tomorrow/yesterday/YYYY-MM-DD 解析为配置时区下的日期。

    注意：这不是自然语言解析器，只是脚本 CLI 的少量便捷关键字。
    复杂表达（如“下周三下午”）由 Codex 负责换算成明确时间后再调用工具。
    """
    today = now().date()
    if value is None:
        return today
    if isinstance(value, datetime):
        return ensure_aware(value).astimezone(get_tz()).date()
    if isinstance(value, date):
        return value
    text = value.strip().lower()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"无法识别的日期: {value!r}（支持 today/tomorrow/yesterday 或 YYYY-MM-DD）"
        ) from exc


def day_bounds(value: str | date | datetime | None = None) -> tuple[datetime, datetime]:
    """返回某一天在配置时区下的 [当天 00:00, 次日 00:00) 时间范围。"""
    day = resolve_day(value)
    start = datetime.combine(day, time.min, tzinfo=get_tz())
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=get_tz())
    return start, end

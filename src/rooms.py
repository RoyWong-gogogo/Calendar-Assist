"""会议室（Exchange room mailbox）地址工具。

会议室邮箱按「ROOM_NAME_PREFIX + 编号 @ ROOM_EMAIL_DOMAIN」规律命名
（如 CDConfRoom808@arraycomm.com），配置见 src/config.py。
本模块只做地址归一化，不访问网络；查询与预订在 src/outlook_service.py。
"""

from __future__ import annotations

import re

from src.config import ROOM_EMAIL_DOMAIN, ROOM_NAME_PREFIX

_NUMBER_RE = re.compile(r"^\d{1,4}$")


def expand_room(value: str) -> str:
    """把会议室输入归一化为完整邮箱地址。

    接受编号（808）、名称（CDConfRoom808）或完整邮箱（CDConfRoom808@域名），
    大小写不敏感（大小写按用户输入保留，仅用于比较前缀）。
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("会议室不能为空")
    if "@" in text:
        local, _, domain = text.partition("@")
        if not local or not domain:
            raise ValueError(f"会议室邮箱格式不正确: {value!r}")
        return text
    if _NUMBER_RE.match(text):
        return f"{ROOM_NAME_PREFIX}{text}@{ROOM_EMAIL_DOMAIN}"
    if text.casefold().startswith(ROOM_NAME_PREFIX.casefold()):
        return f"{text}@{ROOM_EMAIL_DOMAIN}"
    raise ValueError(
        f"无法识别的会议室: {value!r}"
        f"（可传编号如 808、名称如 {ROOM_NAME_PREFIX}808，或完整邮箱）"
    )


def room_label(address: str) -> str:
    """会议室邮箱的显示名（@ 前的本地部分，如 CDConfRoom808）。"""
    return (address or "").split("@")[0]

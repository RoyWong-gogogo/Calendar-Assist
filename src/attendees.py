"""与会人（attendees）增删的纯函数工具。

事件里的与会人数组同时装着普通与会人（required / optional）和会议室
（resource）。本模块只处理普通与会人：会议室由 --room 分支与 src/rooms.py
负责，两边分开才不会在加人时把已订的会议室冲掉。
统一使用简洁格式：{"type", "address", "name", "response"}（见服务的 _attendee_list）。
"""

from __future__ import annotations

from src.contacts import resolve, resolve_addresses

DEFAULT_TYPE = "required"
RESOURCE_TYPE = "resource"


def normalize_address(address) -> str:
    """邮箱地址的比较形式（去空白 + 小写），用于去重与匹配。"""
    return (address or "").strip().lower()


def is_resource(entry: dict) -> bool:
    """是否为会议室 / 设备（resource 类型）与会人。"""
    return (entry.get("type") or "").lower() == RESOURCE_TYPE


def split_people(attendees) -> tuple[list[dict], list[dict]]:
    """把与会人拆成（普通与会人, 会议室）两组，各自保持原有顺序。"""
    people: list[dict] = []
    resources: list[dict] = []
    for entry in attendees or []:
        (resources if is_resource(entry) else people).append(entry)
    return people, resources


def clean_addresses(items) -> list[str]:
    """把「邮箱 或 姓名」列表整理成邮箱地址列表（去掉空白与空项）。

    姓名按通讯录 data/contacts.csv 解析（见 src/contacts.py）；
    既不是邮箱、通讯录里也查不到就报错，避免邀请被静默丢弃。
    在调用方（服务层）发请求前就该跑一遍。
    """
    return resolve_addresses(items)


def merge(people, add=None, remove=None) -> list[dict]:
    """在现有普通与会人上增删，返回简洁格式的新列表。

    - 保持原有顺序，并按邮箱地址去重（大小写不敏感）
    - add 中的新地址追加到末尾，类型默认 required；缺 @ 直接报错，
      避免邀请被静默丢弃（与 create_event 的校验一致）
    - remove 按邮箱地址移除；不在列表里的地址忽略（由调用方负责汇报）
    """
    remove_keys = {normalize_address(item) for item in remove or []}
    remove_keys.discard("")
    result: list[dict] = []
    seen: set[str] = set()
    for entry in people or []:
        address = (entry.get("address") or "").strip()
        key = normalize_address(address)
        if not key or key in seen or key in remove_keys:
            continue
        seen.add(key)
        result.append({
            "type": entry.get("type") or DEFAULT_TYPE,
            "address": address,
            "name": entry.get("name") or None,
            "response": entry.get("response") or None,
        })
    for address in clean_addresses(add):
        key = normalize_address(address)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "type": DEFAULT_TYPE,
            "address": address,
            "name": None,
            "response": None,
        })
    return result


def addresses(entries) -> set[str]:
    """一组与会人的地址集合（比较形式），便于判断某人是否已在列表里。"""
    keys = {normalize_address(entry.get("address")) for entry in entries or []}
    keys.discard("")
    return keys


def describe(entry: dict) -> str:
    """一行显示一个与会人：显示名 <邮箱>，已有明确响应时附上状态。"""
    address = (entry.get("address") or "").strip()
    name = (entry.get("name") or "").strip()
    label = address
    if name and normalize_address(name) != normalize_address(address):
        label = f"{name} <{address}>"
    response = (entry.get("response") or "").strip()
    if response in ("", "none", "notResponded"):
        return label
    return f"{label}（{response}）"

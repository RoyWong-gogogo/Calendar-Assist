"""通讯录：把姓名解析成邮箱地址，让邀请与会人不用每次重新查邮箱。

数据源是 data/contacts.csv（name,address,aliases,note），是唯一事实源：
条目来自历史日历的与会人扫描或用户确认。解析只做**确定性匹配**——
按姓名 / 别名 / 邮箱地址 / 邮箱本地部分比对，比较时忽略大小写与空白；
匹配不到或命中多个就报错并列出候选，绝不猜（见 AGENTS.md「与会人邀请」）。
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

# 项目根目录下的通讯录文件
CONTACTS_PATH = Path(__file__).resolve().parent.parent / "data" / "contacts.csv"
ALIAS_SEPARATOR = ";"


def _key(text) -> str:
    """比较用的键：去掉所有空白并转小写（Qian Zhang / qianzhang 视作同一个）。"""
    return "".join((text or "").split()).lower()


def _local_part(address: str) -> str:
    """邮箱 @ 前面的部分（nzhou@arraycomm.com -> nzhou）。"""
    return address.split("@", 1)[0] if "@" in address else ""


@lru_cache(maxsize=8)
def load_contacts(path: str | None = None) -> tuple[dict, ...]:
    """读取通讯录，返回条目元组（同一路径只读一次）。

    文件不存在时返回空元组——通讯录是加速手段，不是必需品，
    缺文件时调用方会走「直接给邮箱」的路径。
    """
    target = Path(path) if path else CONTACTS_PATH
    if not target.exists():
        return ()
    entries: list[dict] = []
    with target.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            address = (row.get("address") or "").strip()
            if "@" not in address:
                continue
            entries.append({
                "name": (row.get("name") or "").strip() or address,
                "address": address,
                "aliases": [
                    part.strip()
                    for part in (row.get("aliases") or "").split(ALIAS_SEPARATOR)
                    if part.strip()
                ],
                "note": (row.get("note") or "").strip(),
            })
    return tuple(entries)


def _index(contacts) -> dict[str, list[dict]]:
    """建立 键 -> 条目 的索引：姓名 / 别名 / 完整邮箱 / 邮箱本地部分。"""
    index: dict[str, list[dict]] = {}
    for entry in contacts:
        keys = [entry["name"], *entry["aliases"], entry["address"], _local_part(entry["address"])]
        for key in keys:
            normalized = _key(key)
            if not normalized:
                continue
            bucket = index.setdefault(normalized, [])
            if entry not in bucket:
                bucket.append(entry)
    return index


def lookup(text, path: str | None = None) -> list[dict]:
    """按姓名 / 别名 / 邮箱 精确查通讯录，返回全部命中（可能多个）。"""
    return list(_index(load_contacts(path)).get(_key(text), []))


def search(keyword, path: str | None = None) -> list[dict]:
    """模糊查：姓名 / 别名 / 邮箱 / 备注里包含关键词的条目（给人挑选用，不用于写入）。"""
    needle = _key(keyword)
    if not needle:
        return list(load_contacts(path))
    result = []
    for entry in load_contacts(path):
        haystack = _key(" ".join([entry["name"], *entry["aliases"], entry["address"], entry["note"]]))
        if needle in haystack:
            result.append(entry)
    return result


def resolve(value, field: str = "与会人", path: str | None = None) -> str:
    """把「邮箱 或 姓名」解析成邮箱地址。

    含 @ 的输入按邮箱原样返回；否则查通讯录——找不到或命中多个都抛 ValueError，
    由调用方（Codex）把候选转述给用户确认，绝不猜地址。
    """
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field}不能为空")
    if "@" in text:
        return text
    matches = lookup(text, path)
    if not matches:
        raise ValueError(
            f"{field}「{text}」解析失败：既不是邮箱，也不在通讯录 data/contacts.csv 里。"
            "请直接给邮箱，或用 python scripts/contacts.py --query 关键词 查姓名。"
        )
    addresses = []
    for entry in matches:
        if entry["address"] not in addresses:
            addresses.append(entry["address"])
    if len(addresses) > 1:
        detail = ", ".join(f"{e['name']} <{e['address']}>" for e in matches)
        raise ValueError(f"{field}「{text}」在通讯录里对应多个地址（{detail}），请直接给邮箱")
    return addresses[0]


def resolve_addresses(values, field: str = "与会人", path: str | None = None) -> list[str]:
    """批量解析并保持顺序，空项忽略。"""
    result: list[str] = []
    for value in values or []:
        text = (value or "").strip()
        if not text:
            continue
        address = resolve(text, field=field, path=path)
        if address not in result:
            result.append(address)
    return result

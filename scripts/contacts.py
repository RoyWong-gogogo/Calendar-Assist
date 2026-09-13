"""通讯录查询（只读）：姓名 → 邮箱，邀请与会人时不用每次重查一遍。

数据源是 data/contacts.csv（name,address,aliases,note）——条目来自历史日历的
与会人扫描与用户确认，是「姓名 → 邮箱」的唯一事实源（解析逻辑在 src/contacts.py）。
匹配只做确定性比对：姓名 / 别名 / 完整邮箱 / 邮箱本地部分，忽略大小写与空白；
查不到或命中多个都报错，绝不猜地址。

用法（项目根目录）：
    python scripts/contacts.py --query nanqing          # 模糊查（姓名/别名/邮箱/备注）
    python scripts/contacts.py --name "Nanqing Zhou"    # 精确解析，输出邮箱
    python scripts/contacts.py --list                   # 列出全部条目
    python scripts/contacts.py --list --external        # 只列外部联系人
    python scripts/contacts.py --query zhou --json

邀请时可以直接写姓名（脚本内部走同一套解析）：
    python scripts/update_event.py --event-id XXX --attendee "Nanqing Zhou"

补充 / 修正条目：直接编辑 data/contacts.csv（aliases 列用 ; 分隔多个写法）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.contacts import CONTACTS_PATH, load_contacts, lookup, search
from src.targets import EXIT_NEEDS_CHOICE


def is_external(entry: dict) -> bool:
    """外部联系人：note 里标了「外部: 域名」的条目（来自历史日历的与会人）。"""
    return entry.get("note", "").startswith("外部")


def payload(entries) -> list:
    """JSON 输出结构（与 CSV 列一一对应，便于程序读取）。"""
    return [
        {
            "name": entry["name"],
            "address": entry["address"],
            "aliases": entry["aliases"],
            "note": entry["note"],
        }
        for entry in entries
    ]


def print_entry(entry: dict) -> None:
    line = f"- {entry['name']} <{entry['address']}>"
    if entry["aliases"]:
        line += f"  别名: {', '.join(entry['aliases'])}"
    if entry["note"]:
        line += f"  {entry['note']}"
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="查询通讯录（姓名 ↔ 邮箱）")
    parser.add_argument("--query", "-q", help="模糊查询关键词（姓名 / 别名 / 邮箱 / 备注）")
    parser.add_argument("--name", "-n", help="精确解析姓名或邮箱，命中则输出地址")
    parser.add_argument("--list", action="store_true", help="列出全部条目")
    parser.add_argument("--external", action="store_true", help="只看外部联系人（配合 --list / --query）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    args = parser.parse_args()

    if not (args.query or args.name or args.list):
        parser.error("至少给一项：--query 关键词 / --name 姓名 / --list")

    entries = load_contacts()
    if not entries:
        print(f"[通讯录为空] 没读到 {CONTACTS_PATH}（应为 name,address,aliases,note 的 CSV）",
              file=sys.stderr)
        return 1

    # 精确解析：给人直接抄地址用（与 --attendee 姓名 走的是同一套匹配）
    if args.name:
        matches = lookup(args.name)
        if args.external:
            matches = [entry for entry in matches if is_external(entry)]
        addresses = []
        for entry in matches:
            if entry["address"] not in addresses:
                addresses.append(entry["address"])
        if not addresses:
            print(f"通讯录里没有「{args.name}」——换个写法，或用 --query 关键词 模糊找。",
                  file=sys.stderr)
            return EXIT_NEEDS_CHOICE
        if len(addresses) > 1:
            print(f"「{args.name}」在通讯录里对应多个地址，请直接指定邮箱：", file=sys.stderr)
            for entry in matches:
                print_entry(entry)
            return EXIT_NEEDS_CHOICE
        if args.json:
            print(json.dumps(payload(matches[:1]), ensure_ascii=False, indent=2))
        else:
            print(f"{matches[0]['name']} <{addresses[0]}>")
        return 0

    matched = search(args.query) if args.query else list(entries)
    if args.external:
        matched = [entry for entry in matched if is_external(entry)]

    if args.json:
        print(json.dumps(payload(matched), ensure_ascii=False, indent=2))
        return 0

    scope = "（仅外部）" if args.external else ""
    if args.query:
        print(f"通讯录匹配「{args.query}」{scope}: {len(matched)} 条")
    else:
        print(f"通讯录共 {len(matched)} 条{scope}")
    if not matched:
        print("（没有匹配条目；可用 --list 看全部，或直接编辑 data/contacts.csv 补充）")
        return 0
    for entry in matched:
        print_entry(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())

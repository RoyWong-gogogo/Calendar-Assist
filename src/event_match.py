"""确定性的事件匹配（无 AI / 无向量库）。

Codex 负责理解自然语言（"那个壁仞会议"），把关键词传给这里；
本模块只做确定性的文本包含匹配，日历 API 仍是唯一事实源。
"""

from __future__ import annotations


def match_events(events: list[dict], query: str | None) -> list[dict]:
    """按关键词过滤事件，返回标题/地点/备注中包含全部关键词的事件。

    - query 按空白切分为多个关键词，事件需包含**全部**关键词才匹配
      （中文无空格时整串作为一个关键词做子串匹配）
    - 匹配范围：title + location + description（覆盖"人物出现在邀请备注"的场景）
    - 大小写不敏感；query 为 None / 空白时返回全部事件
    """
    if not query or not query.strip():
        return list(events)

    keywords = [k.lower() for k in query.split()]
    matched: list[dict] = []
    for event in events:
        haystack = " \n".join(
            part
            for part in (
                event.get("title") or "",
                event.get("location") or "",
                event.get("description") or "",
            )
        ).lower()
        if all(keyword in haystack for keyword in keywords):
            matched.append(event)
    return matched

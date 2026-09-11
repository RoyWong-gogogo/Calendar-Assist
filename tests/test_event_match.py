"""match_events 确定性匹配的单元测试。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CALENDAR_TIMEZONE
from src.event_match import match_events

TZ = ZoneInfo(CALENDAR_TIMEZONE)


def _event(event_id, title, location=None, description=None):
    return {"id": event_id, "title": title,
            "start": datetime(2026, 9, 14, 15, tzinfo=TZ),
            "end": datetime(2026, 9, 14, 16, tzinfo=TZ),
            "all_day": False, "location": location, "description": description}


EVENTS = [
    _event("1", "壁仞 AI-RAN 项目沟通"),
    _event("2", "壁仞 商务沟通", location="麓湖生态城"),
    _event("3", "客户方案讨论", description="参会人：壁仞 张总"),
    _event("4", "内部周会"),
]


class MatchEventsTests(unittest.TestCase):
    def test_single_keyword_matches_titles(self):
        result = match_events(EVENTS, "壁仞")
        self.assertEqual([ev["id"] for ev in result], ["1", "2", "3"])

    def test_match_in_location(self):
        result = match_events(EVENTS, "麓湖")
        self.assertEqual([ev["id"] for ev in result], ["2"])

    def test_match_in_description(self):
        # 人物关键词出现在邀请备注里也能匹配
        result = match_events(EVENTS, "张总")
        self.assertEqual([ev["id"] for ev in result], ["3"])

    def test_multiple_keywords_are_and(self):
        result = match_events(EVENTS, "壁仞 商务")
        self.assertEqual([ev["id"] for ev in result], ["2"])

    def test_case_insensitive(self):
        result = match_events(EVENTS, "ai-ran")
        self.assertEqual([ev["id"] for ev in result], ["1"])

    def test_no_match_returns_empty(self):
        result = match_events(EVENTS, "不存在的会议")
        self.assertEqual(result, [])

    def test_empty_query_returns_all(self):
        self.assertEqual(len(match_events(EVENTS, None)), 4)
        self.assertEqual(len(match_events(EVENTS, "   ")), 4)


if __name__ == "__main__":
    unittest.main()

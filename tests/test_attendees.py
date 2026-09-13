"""src/attendees.py 的单元测试（纯函数，不碰网络）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.attendees import (
    addresses,
    clean_addresses,
    describe,
    is_resource,
    merge,
    normalize_address,
    split_people,
)

GUEST = {"type": "required", "address": "guest@arraycomm.com", "name": "Guest",
         "response": "accepted"}
ROOM = {"type": "resource", "address": "CDConfRoom801@arraycomm.com",
        "name": "CDConfRoom801", "response": "accepted"}


class NormalizeTests(unittest.TestCase):
    def test_trim_and_lower(self):
        self.assertEqual(normalize_address("  Emma.Zhou@ArrayComm.com "),
                         "emma.zhou@arraycomm.com")
        self.assertEqual(normalize_address(None), "")

    def test_resource_detection(self):
        self.assertTrue(is_resource(ROOM))
        self.assertFalse(is_resource(GUEST))
        self.assertFalse(is_resource({}))


class SplitTests(unittest.TestCase):
    def test_splits_people_and_rooms_in_order(self):
        people, rooms = split_people([GUEST, ROOM, {"type": "optional",
                                                    "address": "b@x.com"}])
        self.assertEqual([e["address"] for e in people],
                         ["guest@arraycomm.com", "b@x.com"])
        self.assertEqual([e["address"] for e in rooms], [ROOM["address"]])

    def test_empty_input(self):
        self.assertEqual(split_people(None), ([], []))


class MergeTests(unittest.TestCase):
    def test_adds_to_existing(self):
        merged = merge([GUEST], add=["new@arraycomm.com"])
        self.assertEqual([e["address"] for e in merged],
                         ["guest@arraycomm.com", "new@arraycomm.com"])
        self.assertEqual(merged[0]["response"], "accepted")  # 保留原状态
        self.assertEqual(merged[1]["type"], "required")
        self.assertIsNone(merged[1]["name"])

    def test_removes_by_address_case_insensitively(self):
        merged = merge([GUEST], remove=["GUEST@ArrayComm.com"])
        self.assertEqual(merged, [])

    def test_duplicate_add_is_ignored(self):
        merged = merge([GUEST], add=["Guest@arraycomm.com", "guest@arraycomm.com"])
        self.assertEqual(len(merged), 1)

    def test_duplicate_existing_entries_collapse(self):
        merged = merge([GUEST, dict(GUEST)])
        self.assertEqual(len(merged), 1)

    def test_blank_entries_ignored(self):
        merged = merge([{"type": "required", "address": "  "}], add=["", "   "])
        self.assertEqual(merged, [])

    def test_clean_addresses_trims_and_validates(self):
        self.assertEqual(clean_addresses([" a@x.com ", "", "  "]), ["a@x.com"])
        with self.assertRaises(ValueError):
            clean_addresses(["nope"])

    def test_invalid_address_raises(self):
        with self.assertRaises(ValueError) as ctx:
            merge([], add=["not-an-email"])
        self.assertIn("不在通讯录", str(ctx.exception))

    def test_add_and_remove_together_keeps_order(self):
        merged = merge([GUEST, ROOM], add=["c@x.com"], remove=["guest@arraycomm.com"])
        self.assertEqual([e["address"] for e in merged],
                         [ROOM["address"], "c@x.com"])

    def test_none_input_returns_empty(self):
        self.assertEqual(merge(None), [])


class DescribeTests(unittest.TestCase):
    def test_name_and_response(self):
        self.assertEqual(describe(GUEST), "Guest <guest@arraycomm.com>（accepted）")

    def test_pending_response_is_omitted(self):
        entry = {"type": "required", "address": "a@x.com", "name": None, "response": "none"}
        self.assertEqual(describe(entry), "a@x.com")

    def test_name_equal_to_address_is_not_repeated(self):
        entry = {"type": "required", "address": "a@x.com", "name": "a@x.com"}
        self.assertEqual(describe(entry), "a@x.com")

    def test_addresses_collects_normalized_keys(self):
        self.assertEqual(addresses([GUEST, {"type": "required", "address": ""}]),
                         {"guest@arraycomm.com"})


if __name__ == "__main__":
    unittest.main()

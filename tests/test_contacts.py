"""src/contacts.py 的单元测试（纯函数 + 临时 CSV，不依赖真实通讯录内容）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.attendees import clean_addresses
from src.contacts import (
    CONTACTS_PATH,
    load_contacts,
    lookup,
    resolve,
    resolve_addresses,
    search,
)

# 临时通讯录：覆盖姓名 / 别名 / 邮箱本地部分 / 重名 / 非法行 / 外部标注
SAMPLE = (
    "name,address,aliases,note\n"
    "Nanqing Zhou,nzhou@arraycomm.com,nzhou;Nanqing,\n"
    "Emma Zhou,Emma.Zhou@arraycomm.com,,\n"
    "Qian Zhang,qzhang@arraycomm.com,小张,\n"
    "Xu Yang,Xu.Yang@arraycomm.com,,\n"
    "Zhou Ming,ZhouMing@arraycomm.com,,外部: example.com\n"
    "Zhou Ming,zming@other.com,zmi,外部: other.com\n"
    "Broken Row,not-an-address,,\n"
)


class TempContactsTests(unittest.TestCase):
    """解析逻辑用临时 CSV 验证，不与真实 data/contacts.csv 的内容耦合。"""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.path = str(Path(cls._dir.name) / "contacts.csv")
        Path(cls.path).write_text(SAMPLE, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def resolve(self, value, **kwargs):
        return resolve(value, path=self.path, **kwargs)

    def test_email_passes_through(self):
        self.assertEqual(self.resolve("nzhou@other.com"), "nzhou@other.com")
        self.assertEqual(self.resolve("  nzhou@other.com  "), "nzhou@other.com")

    def test_exact_name_hit(self):
        self.assertEqual(self.resolve("Nanqing Zhou"), "nzhou@arraycomm.com")

    def test_name_ignores_case_and_spaces(self):
        self.assertEqual(self.resolve("nanqingzhou"), "nzhou@arraycomm.com")
        self.assertEqual(self.resolve("  NANQING ZHOU  "), "nzhou@arraycomm.com")

    def test_alias_and_local_part_hit(self):
        self.assertEqual(self.resolve("Nanqing"), "nzhou@arraycomm.com")
        self.assertEqual(self.resolve("nzhou"), "nzhou@arraycomm.com")
        self.assertEqual(self.resolve("小张"), "qzhang@arraycomm.com")
        self.assertEqual(self.resolve("zmi"), "zming@other.com")

    def test_blank_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.resolve("   ")
        self.assertIn("不能为空", str(ctx.exception))

    def test_unknown_name_raises_with_hint(self):
        with self.assertRaises(ValueError) as ctx:
            self.resolve("Nobody Here")
        self.assertIn("不在通讯录", str(ctx.exception))
        self.assertIn("contacts.py", str(ctx.exception))

    def test_duplicate_name_raises_listing_candidates(self):
        with self.assertRaises(ValueError) as ctx:
            self.resolve("Zhou Ming")
        message = str(ctx.exception)
        self.assertIn("多个地址", message)
        self.assertIn("zming@other.com", message)

    def test_field_name_included_in_message(self):
        with self.assertRaises(ValueError) as ctx:
            self.resolve("Nobody Here", field="收件人")
        self.assertIn("收件人", str(ctx.exception))

    def test_resolve_addresses_keeps_order_and_dedupes(self):
        result = resolve_addresses(
            ["Nanqing Zhou", "nzhou@arraycomm.com", " ", "qzhang"], path=self.path
        )
        self.assertEqual(result, ["nzhou@arraycomm.com", "qzhang@arraycomm.com"])

    def test_lookup_is_exact_match_only(self):
        self.assertEqual(lookup("Zhou", path=self.path), [])
        self.assertEqual(len(lookup("Zhou Ming", path=self.path)), 2)

    def test_search_is_fuzzy(self):
        self.assertEqual(
            [entry["address"] for entry in search("zmi", path=self.path)],
            ["zming@other.com"],
        )
        self.assertEqual(len(search("外部", path=self.path)), 2)

    def test_invalid_rows_are_skipped(self):
        addresses = [entry["address"] for entry in load_contacts(self.path)]
        self.assertNotIn("not-an-address", addresses)
        self.assertEqual(len(addresses), 6)

    def test_missing_file_returns_empty(self):
        missing = str(Path(self._dir.name) / "nope.csv")
        self.assertEqual(load_contacts(missing), ())


class RealContactsFileTests(unittest.TestCase):
    """核对仓库里真实的 data/contacts.csv：数据质量 + 邀请用得到的那几个人。"""

    def test_file_exists_and_loads(self):
        self.assertTrue(CONTACTS_PATH.exists(), f"通讯录文件缺失: {CONTACTS_PATH}")
        self.assertGreaterEqual(len(load_contacts()), 100)

    def test_addresses_valid_and_unique(self):
        addresses = [entry["address"] for entry in load_contacts()]
        self.assertTrue(all("@" in address for address in addresses))
        lowered = [address.lower() for address in addresses]
        self.assertEqual(len(lowered), len(set(lowered)), "通讯录里有重复邮箱地址")

    def test_rooms_are_not_listed_as_people(self):
        rooms = [
            entry for entry in load_contacts()
            if entry["address"].lower().startswith("cdconfroom")
        ]
        self.assertEqual(rooms, [], "会议室邮箱不应出现在通讯录里（用 list_rooms.py 查）")

    def test_known_people_resolve(self):
        expected = {
            "Nanqing Zhou": "nzhou@arraycomm.com",
            "Emma Zhou": "Emma.Zhou@arraycomm.com",
            "Qian Zhang": "qzhang@arraycomm.com",
            "Xu Yang": "Xu.Yang@arraycomm.com",
        }
        for name, address in expected.items():
            self.assertEqual(resolve(name), address, name)

    def test_invite_accepts_name(self):
        self.assertEqual(
            clean_addresses(["Nanqing Zhou", "Xu.Yang@arraycomm.com"]),
            ["nzhou@arraycomm.com", "Xu.Yang@arraycomm.com"],
        )


if __name__ == "__main__":
    unittest.main()

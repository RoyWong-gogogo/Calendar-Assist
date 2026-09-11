"""Outlook 云端点配置的单元测试（不需要网络，也不需要微软凭证）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# 保证可以从项目根目录导入 src 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.outlook_auth import AUTHORITY


class OutlookCloudConfigTests(unittest.TestCase):
    def test_china_endpoints_by_default(self):
        self.assertEqual(
            config.OUTLOOK_AUTHORITY_HOST, "login.partner.microsoftonline.cn"
        )
        self.assertEqual(
            config.GRAPH_BASE_URL, "https://microsoftgraph.chinacloudapi.cn/v1.0"
        )
        self.assertEqual(
            config.OUTLOOK_SCOPES,
            ["https://microsoftgraph.chinacloudapi.cn/Calendars.ReadWrite"],
        )

    def test_authority_combines_host_and_tenant(self):
        self.assertTrue(
            AUTHORITY.startswith("https://login.partner.microsoftonline.cn/")
        )
        self.assertIn(config.OUTLOOK_TENANT_ID, AUTHORITY)

    def test_global_cloud_mapping_available(self):
        self.assertIn("global", config._OUTLOOK_CLOUDS)
        mapping = config._OUTLOOK_CLOUDS["global"]
        self.assertEqual(mapping["authority_host"], "login.microsoftonline.com")
        self.assertEqual(mapping["graph_base"], "https://graph.microsoft.com/v1.0")


if __name__ == "__main__":
    unittest.main()

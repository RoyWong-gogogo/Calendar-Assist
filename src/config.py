"""calendar-agent 配置。

所有配置集中在此处读取（优先级：环境变量 > .env 文件 > 内置默认值）。
时区只在本文件定义一次，其他模块一律从这里导入，禁止散落硬编码。
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "python-dotenv 未安装。请先在虚拟环境中执行: "
        "pip install -r requirements.txt"
    ) from exc

# 项目根目录（src/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 读取项目根目录下的 .env（如果存在；已存在的环境变量优先）
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_path(env_key: str, default: Path) -> Path:
    """读取路径配置；相对路径一律相对于项目根目录解析。"""
    value = os.environ.get(env_key)
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


# 解析“今天/明天”等相对日期、以及 naive datetime 时使用的时区。
CALENDAR_TIMEZONE: str = os.environ.get("CALENDAR_TIMEZONE", "Asia/Shanghai")

# ---- 日历服务提供方 ----
# ics（默认，只读订阅）/ outlook（暂不可用，见下）/ google（过渡期保留）
CALENDAR_PROVIDER: str = os.environ.get("CALENDAR_PROVIDER") or "ics"

# ---- ICS 订阅（当前默认后端）----
# Outlook 网页版「发布日历」生成的 ICS 订阅链接（只读）。
# 注意：链接本身是机密，任何拿到的人都能查看日历，只应保存在 .env。
ICS_URL: str = os.environ.get("ICS_URL") or ""

# ---- Outlook Calendar（Microsoft Graph）----
# Azure App registration 的 Application (client) ID（使用 Outlook 时必填）
OUTLOOK_CLIENT_ID: str = os.environ.get("OUTLOOK_CLIENT_ID") or ""

# Azure App registration 的 Directory (tenant) ID。
# 工作或学校账号建议填写自己组织的租户 ID；留空使用 "organizations"。
OUTLOOK_TENANT_ID: str = os.environ.get("OUTLOOK_TENANT_ID") or "organizations"

# 授权方式: device（设备代码流，默认，无需在 Azure 配置重定向 URI）
#           | interactive（交互式浏览器流程）
OUTLOOK_AUTH_FLOW: str = os.environ.get("OUTLOOK_AUTH_FLOW") or "device"

# MSAL token 缓存文件（首次授权后自动生成）
OUTLOOK_TOKEN_FILE: Path = _resolve_path(
    "OUTLOOK_TOKEN_FILE", PROJECT_ROOT / "credentials" / "outlook_token.bin"
)

# 要操作的 Google 日历 ID，"primary" 即用户主日历。
GOOGLE_CALENDAR_ID: str = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

# Google Cloud Console 下载的 OAuth 客户端密钥文件。
GOOGLE_CREDENTIALS_FILE: Path = _resolve_path(
    "GOOGLE_CREDENTIALS_FILE", PROJECT_ROOT / "credentials" / "credentials.json"
)

# 首次授权后缓存的 OAuth token 文件。
GOOGLE_TOKEN_FILE: Path = _resolve_path(
    "GOOGLE_TOKEN_FILE", PROJECT_ROOT / "credentials" / "token.json"
)

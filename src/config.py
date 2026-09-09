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

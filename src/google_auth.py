"""Google OAuth 凭证获取与缓存。

OAuth 逻辑独立于日历业务代码（业务见 src/calendar_service.py）：
- 优先读取缓存的 token（credentials/token.json）
- token 过期则自动刷新
- 没有有效 token 时，用 credentials/credentials.json 发起本地 OAuth 流程
"""

from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE

# 日程事件读写范围。v0.1 的 list_events 只需要读，但 Session 2 会实现
# create_event，直接申请读写范围可以避免届时要求用户重新授权。
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class AuthError(RuntimeError):
    """OAuth 配置或授权流程出错。"""


def get_credentials() -> Credentials:
    """返回可用的 Google 凭证，必要时自动刷新或发起 OAuth 授权。"""
    creds = _load_cached_token()

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise AuthError(f"刷新 OAuth token 失败: {exc}") from exc
        _save_token(creds)
        return creds

    return _run_oauth_flow()


def _load_cached_token() -> Credentials | None:
    if not GOOGLE_TOKEN_FILE.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), SCOPES)
    except Exception as exc:
        raise AuthError(
            f"读取缓存的 OAuth token 失败（{GOOGLE_TOKEN_FILE}）: {exc}\n"
            "如该 token 已失效或授权范围不匹配，可删除此文件后重新运行以重新授权。"
        ) from exc


def _run_oauth_flow() -> Credentials:
    if not GOOGLE_CREDENTIALS_FILE.exists():
        raise AuthError(
            "未找到 Google OAuth 客户端密钥文件:\n"
            f"  {GOOGLE_CREDENTIALS_FILE}\n"
            "请先完成 Google Cloud 配置（详见 README.md 的 Google Cloud OAuth 配置一节）:\n"
            "  1. 在 https://console.cloud.google.com/ 创建（或选择）一个项目\n"
            "  2. 启用 Google Calendar API（APIs & Services → Library）\n"
            "  3. 配置 OAuth consent screen（External），并把你的 Google 邮箱加入 Test users\n"
            "  4. 创建 OAuth client ID，应用类型选 Desktop app，下载 JSON\n"
            f"  5. 保存为 {GOOGLE_CREDENTIALS_FILE}"
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(GOOGLE_CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=0)
    except Exception as exc:
        raise AuthError(f"Google OAuth 授权流程失败: {exc}") from exc
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    GOOGLE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOOGLE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

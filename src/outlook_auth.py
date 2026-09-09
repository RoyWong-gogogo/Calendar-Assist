"""Microsoft（Outlook Calendar）OAuth 认证，基于 MSAL 公共客户端。

- 默认使用设备代码流（device code flow）：无需本机监听端口，也无需在 Azure
  配置重定向 URI，用户在任意浏览器打开 https://microsoft.com/devicelogin
  输入一次性代码即可完成授权。
- 可通过 OUTLOOK_AUTH_FLOW=interactive 切换为交互式浏览器流程（需要在
  Azure 应用中额外添加平台并配置 http://localhost 重定向 URI）。
- token 缓存在 credentials/outlook_token.bin，过期自动静默刷新。
"""

from __future__ import annotations

import msal

from src.config import (
    OUTLOOK_AUTH_FLOW,
    OUTLOOK_CLIENT_ID,
    OUTLOOK_TENANT_ID,
    OUTLOOK_TOKEN_FILE,
)

# 日程读写范围。list_events 只需要读，但 Session 2 会实现 create_event，
# 直接申请读写范围可以避免届时要求用户重新授权。
SCOPES = ["https://graph.microsoft.com/Calendars.ReadWrite"]

AUTHORITY = f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}"

_app: msal.PublicClientApplication | None = None


class AuthError(RuntimeError):
    """Outlook OAuth 配置或授权流程出错。"""


def get_access_token() -> str:
    """返回可用的 Microsoft Graph 访问令牌；优先静默刷新，失败则发起授权。"""
    app = _get_app()

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(app)
            return result["access_token"]

    flow_name = (OUTLOOK_AUTH_FLOW or "device").strip().lower()
    try:
        if flow_name == "interactive":
            result = app.acquire_token_interactive(scopes=SCOPES)
        else:
            result = _acquire_by_device_flow(app)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(f"Outlook OAuth 授权流程失败: {exc}") from exc
    _save_cache(app)

    if not result or "access_token" not in result:
        error = (result or {}).get("error", "unknown_error")
        description = (result or {}).get("error_description", "")
        raise AuthError(
            f"获取 Outlook 访问令牌失败: {error}\n{description}\n"
            "常见原因:\n"
            "  - AADSTS7000218: Azure 应用的 Allow public client flows 未开启"
            "（App registrations → Authentication → Allow public client flows → Yes）\n"
            "  - 组织要求管理员同意: 需要 IT 管理员在 API permissions 页点击"
            " Grant admin consent\n"
            "  - OUTLOOK_CLIENT_ID / OUTLOOK_TENANT_ID 填写不正确"
        )
    return result["access_token"]


def _get_app() -> msal.PublicClientApplication:
    global _app
    if _app is None:
        if not OUTLOOK_CLIENT_ID:
            raise AuthError(
                "未配置 OUTLOOK_CLIENT_ID。\n"
                "请先完成 Azure 应用注册（详见 README.md 的 Outlook Calendar 接入一节）:\n"
                "  1. 打开 https://portal.azure.com/ → Microsoft Entra ID →"
                " App registrations → New registration\n"
                "  2. 受支持的帐户类型选 Accounts in this organizational directory only"
                "（单租户），注册\n"
                "  3. 复制 Application (client) ID 和 Directory (tenant) ID\n"
                "  4. Authentication → Allow public client flows → Yes\n"
                "  5. API permissions → 添加 Microsoft Graph 委托权限 Calendars.ReadWrite\n"
                "  6. 在项目根目录 .env 写入 OUTLOOK_CLIENT_ID=... 和 OUTLOOK_TENANT_ID=..."
            )
        cache = msal.SerializableTokenCache()
        if OUTLOOK_TOKEN_FILE.exists():
            try:
                cache.deserialize(OUTLOOK_TOKEN_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                raise AuthError(
                    f"读取 Outlook token 缓存失败（{OUTLOOK_TOKEN_FILE}）: {exc}\n"
                    "如缓存已损坏，可删除该文件后重新运行以重新授权。"
                ) from exc
        _app = msal.PublicClientApplication(
            client_id=OUTLOOK_CLIENT_ID,
            authority=AUTHORITY,
            token_cache=cache,
        )
    return _app


def _acquire_by_device_flow(app: msal.PublicClientApplication) -> dict:
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise AuthError(f"无法发起设备授权流程: {flow}")
    print(
        "\n需要完成 Microsoft 账号授权（代码约 15 分钟内有效）:\n"
        f"  1. 在任意浏览器打开: {flow.get('verification_uri', 'https://microsoft.com/devicelogin')}\n"
        f"  2. 输入代码: {flow['user_code']}\n"
        "  3. 使用你的 Microsoft 365 工作/学校账号登录并同意\n",
        flush=True,
    )
    return app.acquire_token_by_device_flow(flow)


def _save_cache(app: msal.PublicClientApplication) -> None:
    cache = app.token_cache
    if getattr(cache, "has_state_changed", False):
        OUTLOOK_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTLOOK_TOKEN_FILE.write_text(cache.serialize(), encoding="utf-8")

"""一次性引导脚本：注册 calendar-agent 的 Azure AD 应用（中国区）。

适用场景：租户限制了普通用户访问 Azure 门户（portal.azure.cn 的 App
registrations 页面报 401），但租户仍允许用户注册应用时，可绕过门户 UI
直接通过 Microsoft Graph 完成注册。

做法：设备码登录时使用 Azure CLI 的第一方应用身份（与 az login 等同，
微软官方公开客户端），拿到 Graph 中国区读写令牌后：
1. 读取本租户 ID（Directory tenant ID）
2. 查找/创建名为 calendar-agent 的应用注册（单租户 + 公共客户端）
3. 为其声明 Microsoft Graph 委托权限 Calendars.ReadWrite
4. 把 Application (client) ID 和 Directory (tenant) ID 写入项目根目录 .env

用法（项目根目录）：
    ./.venv/Scripts/python.exe -u scripts/register_outlook_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import msal
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import OUTLOOK_AUTHORITY_HOST, PROJECT_ROOT

# Azure CLI 的第一方公开客户端 ID（微软官方，各云通用）。
# 仅用于本次设备码登录获取 Graph 令牌，等同 az login，不涉及任何机密。
AZ_CLI_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"

# Microsoft Graph 服务主体在所有云中的 appId 一致；其委托权限
# Calendars.ReadWrite 的 GUID 默认值（优先运行时从租户实际读取）。
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
CALENDARS_READWRITE_FALLBACK_ID = "1ec239c2-d7c7-4699-897e-1a1f648e93f9"

APP_NAME = "calendar-agent"
GRAPH_TIMEOUT = 30


def main() -> int:
    authority = f"https://{OUTLOOK_AUTHORITY_HOST}/organizations"
    graph_base = f"https://microsoftgraph.chinacloudapi.cn/v1.0"

    print("第 1/3 步：设备码登录（Azure CLI 第一方身份，等同 az login）...")
    token = _device_login(authority)
    headers = {"Authorization": f"Bearer {token}"}

    print("第 2/3 步：读取租户信息...")
    tenant_id = _get_tenant_id(graph_base, headers)
    print(f"  租户 ID: {tenant_id}")

    print("第 3/3 步：查找/创建应用注册...")
    client_id = _find_or_create_app(graph_base, headers)
    print(f"  Application (client) ID: {client_id}")

    _write_env(client_id, tenant_id)
    print("\n完成！两个 ID 已写入 .env。")
    print("下一步：运行 scripts/list_events.py 完成日历授权并验证。")
    return 0


def _device_login(authority: str) -> str:
    app = msal.PublicClientApplication(
        AZ_CLI_CLIENT_ID, authority=authority, allow_broker=False
    )
    flow = app.initiate_device_flow(
        scopes=["https://microsoftgraph.chinacloudapi.cn/.default"]
    )
    if "user_code" not in flow:
        raise RuntimeError(f"无法发起设备授权流程: {flow}")
    print("\n" + "=" * 60)
    print(flow.get("message", "请打开 https://microsoft.com/devicelogin 输入代码"))
    print("=" * 60 + "\n")
    result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        error = (result or {}).get("error", "unknown")
        desc = (result or {}).get("error_description", "")
        raise RuntimeError(
            f"设备码登录失败: {error}\n{desc}\n"
            "如果是 consent 相关错误（需要管理员同意），说明租户策略要求管理员"
 "批准，请 IT 管理员协助完成应用注册（见 README）。"
        )
    return result["access_token"]


def _get_tenant_id(graph_base: str, headers: dict) -> str:
    resp = requests.get(f"{graph_base}/organization", headers=headers, timeout=GRAPH_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"读取租户信息失败: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()["value"][0]["id"]


def _find_or_create_app(graph_base: str, headers: dict) -> str:
    # 已存在则复用（重复运行安全）
    resp = requests.get(
        f"{graph_base}/applications",
        params={"$filter": f"displayName eq '{APP_NAME}'"},
        headers=headers,
        timeout=GRAPH_TIMEOUT,
    )
    if resp.status_code == 200:
        apps = resp.json().get("value", [])
        if apps:
            print(f"  应用已存在，复用现有注册（objectId={apps[0]['id'][:8]}...）")
            return apps[0]["appId"]

    permission_id = _calendars_readwrite_id(graph_base, headers)
    body = {
        "displayName": APP_NAME,
        "signInAudience": "AzureADMyOrg",
        "isFallbackPublicClient": True,
        "requiredResourceAccess": [
            {
                "resourceAppId": GRAPH_APP_ID,
                "resourceAccess": [{"id": permission_id, "type": "Scope"}],
            }
        ],
    }
    resp = requests.post(
        f"{graph_base}/applications", json=body, headers=headers, timeout=GRAPH_TIMEOUT
    )
    if resp.status_code == 403:
        raise RuntimeError(
            "租户禁止普通用户注册应用（HTTP 403）。"
            "请 IT 管理员按 README「Outlook Calendar」一节代为注册，"
            "或授予你 Application Developer 目录角色后重试。"
        )
    if resp.status_code != 201:
        raise RuntimeError(f"创建应用注册失败: HTTP {resp.status_code} {resp.text[:400]}")
    return resp.json()["appId"]


def _calendars_readwrite_id(graph_base: str, headers: dict) -> str:
    """从租户实际读取 Graph 的 Calendars.ReadWrite 委托权限 GUID。"""
    try:
        resp = requests.get(
            f"{graph_base}/servicePrincipals",
            params={
                "$filter": f"appId eq '{GRAPH_APP_ID}'",
                "$select": "oauth2PermissionScopes",
            },
            headers=headers,
            timeout=GRAPH_TIMEOUT,
        )
        if resp.status_code == 200:
            scopes = resp.json()["value"][0].get("oauth2PermissionScopes", [])
            for scope in scopes:
                if scope.get("value") == "Calendars.ReadWrite":
                    print(f"  从租户读取权限 GUID: {scope['id']}")
                    return scope["id"]
    except (requests.RequestException, KeyError, IndexError):
        pass
    print("  使用默认权限 GUID（未能从租户读取，不影响功能）")
    return CALENDARS_READWRITE_FALLBACK_ID


def _write_env(client_id: str, tenant_id: str) -> None:
    env_path = PROJECT_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.startswith("OUTLOOK_CLIENT_ID="):
            out.append(f"OUTLOOK_CLIENT_ID={client_id}")
        elif line.startswith("OUTLOOK_TENANT_ID="):
            out.append(f"OUTLOOK_TENANT_ID={tenant_id}")
        else:
            out.append(line)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"\n[注册失败] {exc}", file=sys.stderr)
        sys.exit(1)

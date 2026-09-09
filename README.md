# calendar-agent

轻量级个人日程助手。**Codex 对话窗口就是交互入口**：直接用自然语言问日程、约会议、找空档，Codex 调用本项目中的工具读写日历，并把结果告诉你。

**当前默认接入 Outlook Calendar（Microsoft Graph API）**。Google Calendar 无法完成登录，因此切换到微软体系；Google 实现过渡期保留，可通过 `CALENDAR_PROVIDER=google` 切换，Outlook 验证通过后将移除。

**配置的日历服务是唯一日程事实源** —— 所有日程查询都实际读取日历 API，不依赖聊天记录。

## 当前功能

| 能力 | 状态 |
| --- | --- |
| 查询日程 `list_events` | 已实现（Outlook + Google 双后端） |
| 创建日程 `create_event` | 计划 Session 2 |
| 查询空闲时间 `find_free_time` | 计划 Session 2 |

修改、删除日程暂不支持。

## 环境要求

- Windows + PowerShell
- Python 3.11+（开发环境为 3.14）
- 一个 Microsoft 365 工作/学校账号（当前后端）

## 安装

```powershell
py -3.14 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Outlook Calendar 接入（当前默认）

### 第 1 步：注册 Azure 应用（一次性，人工步骤）

使用你的 Microsoft 365 工作/学校账号：

1. 打开 <https://portal.azure.com/>，进入 **Microsoft Entra ID → App registrations → New registration**。
   如果组织禁止普通用户注册应用，需要请 IT 管理员协助完成本步。
2. 填写并注册：
   - Name：`calendar-agent`
   - Supported account types：**Accounts in this organizational directory only (Single tenant)**
   - Redirect URI：留空（设备代码流不需要）
3. 注册完成后，在 Overview 页复制两个值：
   - **Application (client) ID** → 填入 `.env` 的 `OUTLOOK_CLIENT_ID`
   - **Directory (tenant) ID** → 填入 `.env` 的 `OUTLOOK_TENANT_ID`
4. 左侧 **Authentication** → 底部 **Allow public client flows** → 选 **Yes** → Save。
   （设备代码流必需；不改这项登录时会报 AADSTS7000218）
5. 左侧 **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → 勾选 **Calendars.ReadWrite** → **Add permissions**。
   - 如果登录时提示需要管理员批准，说明组织策略要求管理员同意，需要 IT 管理员在该页面点击 **Grant admin consent for <组织名>**。

### 第 2 步：填写 .env

项目根目录创建 `.env`（已被 Git 忽略；也可直接编辑已生成的模板）：

```ini
OUTLOOK_CLIENT_ID=粘贴-Application-client-ID
OUTLOOK_TENANT_ID=粘贴-Directory-tenant-ID
```

### 第 3 步：首次授权并验证

```powershell
./.venv/Scripts/python.exe scripts/list_events.py
```

默认使用**设备代码流**：脚本会打印一个链接和一次性代码，在任意浏览器打开 <https://microsoft.com/devicelogin>，输入代码，用工作/学校账号登录并同意授权。成功后 token 缓存到 `credentials/outlook_token.bin`，之后自动刷新，无需重复登录。

> 权限说明：申请的是委托权限 `Calendars.ReadWrite`（读写）。当前只用到读取，但为了后续实现创建日程时不需要重新授权，一开始就申请了读写范围。

## Google Calendar（过渡期保留）

Google 无法登录后暂未使用，代码保留在 `src/google_auth.py` / `src/calendar_service.py`，Outlook 验证通过后将删除。如需临时切回：在 `.env` 中设置 `CALENDAR_PROVIDER=google`，并按原流程配置（Google Cloud 项目 → 启用 Calendar API → OAuth consent screen（External + Testing，邮箱加入 Test users）→ 创建 Desktop app 类型的 OAuth client ID → JSON 保存为 `credentials/credentials.json`）。

## 使用

```powershell
./.venv/Scripts/python.exe scripts/list_events.py                     # 今天
./.venv/Scripts/python.exe scripts/list_events.py --date tomorrow     # 明天
./.venv/Scripts/python.exe scripts/list_events.py --date 2026-09-12   # 指定日期
./.venv/Scripts/python.exe scripts/list_events.py --from 2026-09-10T09:00 --to 2026-09-10T18:00
./.venv/Scripts/python.exe scripts/list_events.py --json              # JSON 输出
```

## 配置

复制 `.env.example` 为 `.env` 按需修改（不创建 `.env` 时使用内置默认值）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CALENDAR_PROVIDER` | `outlook` | 日历后端：`outlook` / `google`（过渡期） |
| `CALENDAR_TIMEZONE` | `Asia/Shanghai` | 解析日期时间的默认时区（IANA 名称） |
| `OUTLOOK_CLIENT_ID` | （空） | Azure App registration 的 Application (client) ID |
| `OUTLOOK_TENANT_ID` | `organizations` | Azure Directory (tenant) ID，工作/学校账号建议填写 |
| `OUTLOOK_AUTH_FLOW` | `device` | `device` 设备代码流 / `interactive` 浏览器流程（后者需在 Azure 配置重定向 URI） |
| `OUTLOOK_TOKEN_FILE` | `credentials/outlook_token.bin` | MSAL token 缓存路径 |
| `GOOGLE_CALENDAR_ID` | `primary` | Google 日历 ID（仅 provider=google） |
| `GOOGLE_CREDENTIALS_FILE` | `credentials/credentials.json` | Google OAuth 客户端 JSON（仅 provider=google） |
| `GOOGLE_TOKEN_FILE` | `credentials/token.json` | Google token 缓存（仅 provider=google） |

## 项目结构

```
├── AGENTS.md                 # Codex 工作守则（新 Session 必读）
├── README.md
├── requirements.txt
├── .env / .env.example       # 本机配置 / 配置模板
├── .gitignore
├── credentials/              # OAuth 凭证与 token（不提交 Git）
│   └── README.md
├── src/
│   ├── config.py             # 配置：后端、时区、路径、账号 ID
│   ├── service_factory.py    # 按 CALENDAR_PROVIDER 选择后端
│   ├── outlook_auth.py       # Microsoft OAuth（MSAL，设备代码流）
│   ├── outlook_service.py    # Microsoft Graph 日历封装
│   ├── google_auth.py        # Google OAuth（过渡期保留）
│   ├── calendar_service.py   # Google Calendar 封装（过渡期保留）
│   └── datetime_utils.py     # timezone-aware 日期时间工具
├── scripts/
│   └── list_events.py        # 查询日程
└── tests/
    ├── test_datetime_utils.py
    └── test_outlook_parsing.py
```

## 安全注意

以下内容**绝不能提交 Git**（`.gitignore` 已排除）：

- `credentials/` 中的所有凭证与 token（`outlook_token.bin`、`credentials.json`、`token.json`）
- `.env`
- `.venv/`

## 开发计划

- Session 1：项目骨架 + Google OAuth + `list_events`（已完成）
- 切换：Outlook Calendar 接入（当前，进行中）
- Session 2：`create_event` + `find_free_time`
- 之后：验证 Outlook 稳定后删除 Google 实现；按需评估修改、删除日程

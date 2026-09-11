# calendar-agent

轻量级个人日程助手。**Codex 对话窗口就是交互入口**：直接用自然语言问日程、约会议、找空档，Codex 调用本项目中的工具读写日历，并把结果告诉你。

**当前主后端为 Outlook Calendar（中国区 Microsoft Graph OAuth，世纪互联租户）**；ICS 订阅链接作为只读后备。Google 实现过渡期保留，可通过 `CALENDAR_PROVIDER=google` 切换。

**配置的日历服务是唯一日程事实源** —— 所有日程查询都实际读取日历 API，不依赖聊天记录。

## 当前功能

| 能力 | 状态 |
| --- | --- |
| 查询日程 `list_events` | 已实现（ICS / Outlook / Google 多后端） |
| 创建日程 `create_event` | 已实现（Outlook 后端；ICS 只读 / Google 不可用，调用会明确报错） |
| 查询空闲时间 `find_free_time` | 已实现（全部后端；v0.1 将日历上所有事件视为忙碌） |

修改、删除日程暂不支持；测试创建的日程需要在 Outlook 网页版手动删除。

## 环境要求

- Windows + PowerShell
- Python 3.11+（开发环境为 3.14）
- 一个能登录 Azure 中国门户（portal.azure.cn）的工作账号（用于注册应用）

## 安装

```powershell
py -3.14 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## ICS 订阅（只读后备）

后备方案（`CALENDAR_PROVIDER=ics`）：通过 **Outlook 网页版「发布日历」生成的 ICS 订阅链接**只读访问工作日历。无需 OAuth、无需应用注册、无需任何额外账号。

背景：工作邮箱是**世纪互联运营的 Microsoft 365**（`partner.outlook.cn`），它与全球版 Azure / Microsoft 账号体系完全隔离——这正是之前 Azure 门户登录接连报错（AADSTS500011 等）的原因：世纪互联的工作账号在全球门户里根本不存在，全球 OAuth 端点（`login.microsoftonline.com` / `graph.microsoft.com`）也无法认证该账号。正确路径是中国区门户 portal.azure.cn 与中国区端点（见下文 Outlook Calendar 一节）。

### 配置步骤

1. 打开 Outlook 网页版 → 右上角设置（齿轮）→ **日历 → 共享日历**（直达：<https://partner.outlook.cn/calendar/options/calendar/SharedCalendars>）。
2. 找到 **发布日历 (Publish a calendar)** 区域（注意不是上面的 "Share a calendar"，那是共享给其他人用的）。
3. 选择你的主日历 → 点击 **Publish**。
4. 生成两个链接：**复制 ICS 链接**（用于订阅的那个，不是 HTML 链接）。
5. 粘贴到项目根目录 `.env` 的 `ICS_URL=` 后面。

### 限制（重要）

- **只读**：可以查询日程和计算空闲时间，但**无法创建 / 修改 / 删除日程**。需要写入时切换 Outlook 后端（`CALENDAR_PROVIDER=outlook`）。
- **非实时**：发布的是快照，日程改动通常延迟若干分钟甚至更久才会反映到链接里。
- **链接即凭证**：任何拿到 ICS 链接的人都能查看日历内容，只保存在 `.env`，不要提交 Git、不要发给他人。
- 发布内容的详细程度（是否包含标题 / 地点 / 备注）由发布选项决定；如果组织策略禁用发布，Publish 按钮会不可用。

## Outlook Calendar（当前主后端，中国区 Graph OAuth）

`src/outlook_auth.py` / `src/outlook_service.py` 实现完整的 Microsoft Graph OAuth 路径（MSAL 设备码流 + Graph API）。工作邮箱是**世纪互联运营的 Microsoft 365**，必须走中国区端点——门户 portal.azure.cn、登录 `login.partner.microsoftonline.cn`、API `microsoftgraph.chinacloudapi.cn`；由 `.env` 的 `OUTLOOK_CLOUD=china` 控制（`global` 为全球版），代码无需修改。

### 第 1 步：在 Azure 中国门户注册应用（一次性）

用工作账号登录 <https://portal.azure.cn/>（无订阅不影响，应用注册不需要订阅）：

> **门户报 401（You don't have access）时的替代方案**：部分租户（如 ARRAYCOMM）限制普通用户访问门户的 Entra 管理区域，但允许用户注册应用。此时可运行 `scripts/register_outlook_app.py`（Azure CLI 第一方身份设备码登录 + Graph API 注册，自动把两个 ID 写入 `.env`）。若脚本也报 403（租户禁止用户注册应用），则需要 IT 管理员按下述步骤代为注册，或授予 Application Developer 角色。

1. 顶部搜索 **应用注册 (App registrations)**（或首页 "Manage Microsoft Entra ID" 卡片 → View → 左侧 Applications → App registrations）。
2. **New registration**：Name 填 `calendar-agent`；Supported account types 选 **Accounts in this organizational directory only（单租户）**；Redirect URI 留空（设备代码流不需要），注册。
3. Overview 页复制两个值填入 `.env`：**Application (client) ID** → `OUTLOOK_CLIENT_ID`；**Directory (tenant) ID** → `OUTLOOK_TENANT_ID`。
4. 左侧 **Authentication** → 底部 **Allow public client flows** → **Yes** → Save（设备代码流必需，否则报 AADSTS7000218）。
5. 左侧 **API permissions** → Add a permission → **Microsoft Graph** → **Delegated permissions** → 勾选 **Calendars.ReadWrite** → Add permissions。若授权时提示需管理员批准，请管理员在该页点 **Grant admin consent**。

### 第 2 步：首次授权并验证

```powershell
./.venv/Scripts/python.exe scripts/list_events.py
```

默认**设备代码流**：脚本打印链接和一次性代码，在浏览器打开 https://microsoft.com/devicelogin 输入代码，用工作账号登录并同意。成功后 token 缓存到 `credentials/outlook_token.bin`，自动刷新。

> 权限申请的是委托权限 `Calendars.ReadWrite`（读写）。当前只用到读取，但为 Session 2 的 `create_event` 不需要重新授权，直接申请了读写范围。

### 全球版端点（参考）

`OUTLOOK_CLOUD=global` 切回全球端点（login.microsoftonline.com / graph.microsoft.com），适用于全球版 Microsoft 365 账号。以下为此前的全球版注册说明，保留供参考。

### 第 1 步：注册 Azure 应用（一次性，人工步骤）

有两条路径，**当前采用路径 B**（公司工作账号登录 Azure 门户时报 AADSTS500011，路径 A 走不通）。

#### 路径 A：用工作账号注册单租户应用（组织允许时）

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

#### 路径 B：用个人 Microsoft 账号注册多租户应用（当前采用的兜底）

前提：有一个个人 Microsoft 账号（outlook.com / hotmail.com / live.com）。应用注册在个人账号自己的默认目录下，公司不参与注册；日历数据仍通过**工作账号**授权读写，与工作邮箱日历完全互通（会议邀请照常落在工作日历；Session 2 的 create_event 发出的邀请也来自工作邮箱）。

1. 用无痕窗口打开 <https://portal.azure.com/>，用**个人** Microsoft 账号登录。首次进入会自动获得一个 Default Directory，没有 Azure 订阅也能注册应用（忽略"没有订阅"的提示，在顶部搜索框搜 **App registrations**）。
2. **New registration**，填写：
   - Name：`calendar-agent`
   - Supported account types：**Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts**
   - Redirect URI：留空（设备代码流不需要）
3. 在 Overview 页复制 **Application (client) ID** → 填入 `.env` 的 `OUTLOOK_CLIENT_ID`。
4. 左侧 **Authentication** → 底部 **Allow public client flows** → **Yes** → Save。（设备代码流必需，不改会报 AADSTS7000218）
5. 左侧 **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions** → 勾选 **Calendars.ReadWrite** → **Add permissions**。

路径 B 首次授权时（设备码登录）有两种可能结果，取决于组织的用户同意策略：

- 同意页直接放行 → 授权完成，正常读写工作日历。
- 提示**"需要管理员批准 / Approval required"** → 组织只允许管理员同意 `Calendars.ReadWrite` 这类高影响权限，兜底路径走不通，只能请 IT 管理员批准该应用，或按路径 A 在组织内注册。

两点透明说明：授权成功后，该应用会以"用户已同意的应用"出现在公司租户的 Enterprise applications 列表里（严格的 IT 环境能看到）；应用注册方是你的个人账号，请仅自用。若设备码流程被组织的条件访问策略阻止，可在 `.env` 设 `OUTLOOK_AUTH_FLOW=interactive`（需在 Azure 给应用添加 http://localhost 重定向 URI）。

### 第 2 步：填写 .env

项目根目录创建 `.env`（已被 Git 忽略；也可直接编辑已生成的模板）：

```ini
OUTLOOK_CLIENT_ID=粘贴-Application-client-ID
# 路径 A：粘贴 Directory (tenant) ID；路径 B（当前）：organizations
OUTLOOK_TENANT_ID=organizations
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

# 创建日程（--end 与 --duration 二选一）
./.venv/Scripts/python.exe scripts/create_event.py --title "和王总开会" --start 2026-09-14T15:00 --duration 60
./.venv/Scripts/python.exe scripts/create_event.py --title "方案评审" --start 2026-09-15T14:00 --end 2026-09-15T15:30 --location "会议室 A" --description "评审 v2 方案"

# 查找空闲时间（返回所有可容纳该时长的连续区间）
./.venv/Scripts/python.exe scripts/find_free_time.py --from 2026-09-14T09:00 --to 2026-09-14T18:00 --duration 60
```

## 配置

复制 `.env.example` 为 `.env` 按需修改（不创建 `.env` 时使用内置默认值）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CALENDAR_PROVIDER` | `outlook` | 日历后端：`outlook` / `ics` / `google` |
| `OUTLOOK_CLOUD` | `china` | 微软云：`china`（世纪互联）/ `global`（全球） |
| `ICS_URL` | （空） | Outlook「发布日历」生成的 ICS 订阅链接（仅 provider=ics 时必填；机密，等同凭证） |
| `CALENDAR_TIMEZONE` | `Asia/Shanghai` | 解析日期时间的默认时区（IANA 名称） |
| `OUTLOOK_CLIENT_ID` | （空） | Azure App registration 的 Application (client) ID |
| `OUTLOOK_TENANT_ID` | `organizations` | App registration Overview 页的 Directory (tenant) ID；留空使用 `organizations` |
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
│   ├── ics_service.py        # ICS 订阅后端（只读后备）
│   ├── outlook_auth.py       # Microsoft OAuth（MSAL 设备码流，中国区）
│   ├── outlook_service.py    # Microsoft Graph 日历封装（中国区，读+写）
│   ├── free_time.py          # 空闲时间纯算法（后端无关）
│   ├── google_auth.py        # Google OAuth（过渡期保留）
│   ├── calendar_service.py   # Google Calendar 封装（过渡期保留）
│   └── datetime_utils.py     # timezone-aware 日期时间工具
├── scripts/
│   ├── list_events.py        # 查询日程
│   ├── create_event.py       # 创建日程
│   ├── find_free_time.py     # 查找空闲时间
│   └── register_outlook_app.py # 应用注册引导（门户被租户限制时的一次性工具）
└── tests/
    ├── test_datetime_utils.py
    ├── test_free_time.py
    ├── test_create_event.py
    ├── test_ics_parsing.py
    ├── test_outlook_cloud.py
    └── test_outlook_parsing.py
```

## 安全注意

以下内容**绝不能提交 Git**（`.gitignore` 已排除）：

- `credentials/` 中的所有凭证与 token（`outlook_token.bin`、`credentials.json`、`token.json`）
- `.env`
- `.venv/`

## 开发计划

- Session 1：项目骨架 + OAuth + `list_events`（已完成；历经 Google → Outlook 全球端点 → 世纪互联中国区端点的摸索，最终落在中国区 Graph）
- Session 2：`create_event` + `find_free_time`（已完成，基于中国区 Graph 读写）
- 之后候选：`create_event` 支持与会人（自动发会议邀请）、修改 / 删除日程、`find_free_time` 区分 showAs 空闲状态、清理 Google / ICS 备用后端

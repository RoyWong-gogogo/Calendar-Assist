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
| 修改日程 `update_event` | 已实现（Outlook 后端；默认执行，`--dry-run` 预览，写后事后提醒） |
| 删除日程 `delete_event` | 已实现（Outlook 后端；默认执行，`--dry-run` 预览） |
| 事件搜索 `search_events` | 已实现（时间范围 + 关键词确定性匹配） |
| 会议室查询 `list_rooms` | 已实现（仅 Outlook 后端；中国区 Graph 无会议室清单接口，按邮箱命名规律扫描） |
| 会议室预订 | 已实现（`create_event --room` / `update_event --room`，会议室以 resource 与会人写入事件） |
| 邀请与会人 | 已实现（`create_event --attendee` / `update_event --attendee` / `--remove-attendee`，required 类型邀请） |
| 通讯录（姓名 → 邮箱） | 已实现（`data/contacts.csv` 唯一事实源；`scripts/contacts.py` 查询；邀请时 `--attendee 姓名` 自动解析，查不到 / 命中多个都会停下） |

修改 / 删除改为**一条命令完成定位与写入**：`--query 关键词` 配 `--date`（或 `--from`/`--to`）由脚本自己读日历过滤，**恰好 1 个命中即执行**；0 命中或 ≥2 个候选会停下（退出码 4）列出候选或报告没找到，由你指定是哪一个。写操作不做事前冲突 / 忙闲预检（每次预检都是一次额外往返），改为写完后读一次目标时段做**事后提醒**（`--no-notice` 可跳过）；`--dry-run` 只看不改，`--yes` 保留为兼容空参数。

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

## 会议室（CDConfRoom）

会议室是 Exchange **room mailbox**（资源邮箱，形如 `CDConfRoom808@arraycomm.com`），和"地点文本"是两回事：只有把会议室作为 **resource 与会人** 写进事件，才会真正占用会议室日历；只写 `--location` 只是一个标签。

中国区 Graph 的常规"会议室清单"接口都走不通（2026-09 实测）：

| 接口 | 实测结果 | 原因 |
| --- | --- | --- |
| `GET /me/findRooms` | 403 Authorization_RequestDenied | 需要额外委托权限（当前应用只有 `Calendars.ReadWrite`） |
| `GET /places/microsoft.graph.room` | 403 UnknownError | Places API 未在中国区开放 |
| `POST /me/findMeetingTimes` | 405 | 中国区 Graph 未提供该端点 |

可行路径是**命名规律 + 忙闲查询**：`POST /me/calendar/getSchedule`（`Calendars.ReadWrite` 即可）能查询任意邮箱（含会议室）的忙闲，因此按「前缀 + 编号 @ 域名」扫描编号区间就能确认哪些会议室真实存在。

```powershell
./.venv/Scripts/python.exe scripts/list_rooms.py --date 2026-09-15          # 扫描编号 800-850，列出存在的会议室与占用
./.venv/Scripts/python.exe scripts/list_rooms.py --from 2026-09-15T10:00 --to 2026-09-15T11:00 --json

# 预订 / 更换 / 取消会议室
./.venv/Scripts/python.exe scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --room 803
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --room ""
```

- `--room` 接受编号（`801`）、名称（`CDConfRoom801`）或完整邮箱；预订不做事前忙闲预检，直接发出邀请，结果看事件里该会议室与会人的响应状态——`accepted` = 已订上，`declined` = 房间拒绝该时段（需换一间），`none` = 尚未响应（稍后查事件确认）。要挑房间时先跑 `list_rooms.py` 看忙闲。
- 前缀与域名可用 `.env` 的 `ROOM_NAME_PREFIX` / `ROOM_EMAIL_DOMAIN` 覆盖，扫描区间用 `--first` / `--last`。
- 本租户实测存在的会议室：`CDConfRoom801` `802` `803` `804` `805` `808`（600 / 700 / 900 编号段均无房间）。
- 会议室是否自动接受邀请取决于 Exchange 会议室策略；脚本负责发出邀请，若房间配置为冲突自动拒绝，邀请会被拒。
- 本租户实测：会议室**自动接受**邀请（事件与会人 status.response = accepted，约 1 秒内完成）。但**跨邮箱忙闲缓存有延迟**——刚预订完的几分钟内，`getSchedule` / `list_rooms` 可能仍把该会议室显示为空闲，判断预订结果请以事件里会议室与会人的响应状态为准。

## 与会人（会议邀请）

与会人和会议室是同一个 attendees 数组：普通与会人（required / optional）+ 会议室（resource）。`--attendee` / `--remove-attendee` 只增删普通与会人，不会碰已订的会议室；只有显式给 `--room` 才会替换会议室条目。

```powershell
./.venv/Scripts/python.exe scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --attendee nzhou@arraycomm.com
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --attendee emma.zhou@arraycomm.com --attendee qzhang@arraycomm.com
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --remove-attendee emma.zhou@arraycomm.com

# 直接写姓名更省事：走通讯录 data/contacts.csv 解析，结果与写邮箱等价
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --attendee "Nanqing Zhou" --attendee "Xu Yang"
./.venv/Scripts/python.exe scripts/contacts.py --name "Nanqing Zhou"   # 先查地址
./.venv/Scripts/python.exe scripts/contacts.py --query zhou            # 模糊找
```

- `--attendee` 可重复传入，类型为 required（必须参加）；邮箱缺 `@` 在发请求前直接报错，重复邀请按地址去重（大小写不敏感）。
- 写 attendees 时 Graph 按新数组整体覆盖，已有与会人会被重新提交（响应状态可能重置），这是 Exchange 的语义。
- 邀请结果看事件里各与会人的响应状态（`accepted` / `declined` / `none`，刚发出时均为 `none`）；`update_event.py` 写完会把与会人连同响应状态打印出来。
- 邮箱地址走通讯录 `data/contacts.csv`：解析只做确定性匹配（姓名 / 别名 / 完整邮箱 / 邮箱本地部分，忽略大小写与空白），查不到或命中多个都报错停下，不会猜一个地址。中国区 Graph 没有可用的通讯录搜索（`/me/people` 的 `$search` 实测返回 400）；新联系人可从历史日程的与会人里按姓名查找，或向用户确认后补进 CSV。

### 通讯录（data/contacts.csv）

姓名 → 邮箱的本地通讯录，邀请时不用每次重查地址。文件是唯一事实源，列为 `name,address,aliases,note`（UTF-8；`aliases` 用 `;` 分隔多个写法；外部联系人 `note` 写「外部: 域名」）。初始 196 条来自历史日历（2025-09 ~ 2026-09）的与会人扫描：132 个内部地址 + 64 个外部地址，已排除会议室邮箱。

```powershell
./.venv/Scripts/python.exe scripts/contacts.py --list                # 全部条目
./.venv/Scripts/python.exe scripts/contacts.py --list --external     # 只看外部联系人
./.venv/Scripts/python.exe scripts/contacts.py --name "Emma Zhou"    # 精确解析（查不到 / 命中多个 → 退出码 4）
./.venv/Scripts/python.exe scripts/contacts.py --query zhou --json   # 模糊查，JSON 输出
```

- 解析顺序：姓名 / 别名 / 完整邮箱 / 邮箱本地部分，比较时忽略大小写与空白——`Nanqing Zhou`、`nanqingzhou`、`nzhou` 都能命中 `nzhou@arraycomm.com`；含 `@` 的输入按邮箱原样使用。
- 解析在发请求前完成，**查不到或命中多个都停下报错**（邀请时退出码 2，查询时退出码 4），不会把邀请静默丢弃，也不会猜地址。
- 补充 / 修正：直接编辑 `data/contacts.csv`，把别的写法（英文名、中文名、拼音）填进 `aliases` 列即可，不需要改代码。

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
./.venv/Scripts/python.exe scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801   # 预订 CDConfRoom801

# 会议室清单与占用（中国区 Graph 无会议室清单接口，按邮箱命名规律扫描）
./.venv/Scripts/python.exe scripts/list_rooms.py --date 2026-09-15
./.venv/Scripts/python.exe scripts/list_rooms.py --from 2026-09-15T10:00 --to 2026-09-15T11:00 --json

# 查找空闲时间（返回所有可容纳该时长的连续区间）
./.venv/Scripts/python.exe scripts/find_free_time.py --from 2026-09-14T09:00 --to 2026-09-14T18:00 --duration 60

# 搜索日程（只查不改；--query 定位已并入 update / delete）
./.venv/Scripts/python.exe scripts/search_events.py --date 2026-09-14 --query 雅江

# 通讯录（姓名 → 邮箱；邀请时可直接 --attendee "姓名"）
./.venv/Scripts/python.exe scripts/contacts.py --query nanqing
./.venv/Scripts/python.exe scripts/contacts.py --name "Nanqing Zhou"
./.venv/Scripts/python.exe scripts/contacts.py --list --external

# 修改日程（默认直接执行；--query 一条命令定位并改）
./.venv/Scripts/python.exe scripts/update_event.py --query 壁仞 --date tomorrow --start 2026-09-14T16:00 --duration 60
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60          # 已有 id 时
./.venv/Scripts/python.exe scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60 --dry-run # 只看不改

# 删除日程（默认直接执行；--query 一条命令定位并删）
./.venv/Scripts/python.exe scripts/delete_event.py --query 客户会议 --date tomorrow
./.venv/Scripts/python.exe scripts/delete_event.py --event-id <id>                 # 已有 id 时
./.venv/Scripts/python.exe scripts/delete_event.py --event-id <id> --dry-run       # 只看不删
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
| `ROOM_NAME_PREFIX` | `CDConfRoom` | 会议室邮箱前缀（形如 `CDConfRoom808@arraycomm.com`） |
| `ROOM_EMAIL_DOMAIN` | `arraycomm.com` | 会议室邮箱域名 |
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
├── data/
│   └── contacts.csv          # 通讯录（姓名/邮箱/别名/备注，来自历史日历与会人扫描）
├── src/
│   ├── config.py             # 配置：后端、时区、路径、账号 ID
│   ├── service_factory.py    # 按 CALENDAR_PROVIDER 选择后端
│   ├── ics_service.py        # ICS 订阅后端（只读后备）
│   ├── outlook_auth.py       # Microsoft OAuth（MSAL 设备码流，中国区）
│   ├── outlook_service.py    # Microsoft Graph 日历封装（中国区，读+写+改+删）
│   ├── rooms.py              # 会议室邮箱地址归一化（编号 / 名称 / 邮箱）
│   ├── free_time.py          # 空闲时间纯算法（后端无关）
│   ├── conflicts.py          # 冲突检测纯算法（后端无关）
│   ├── event_match.py        # 事件关键词匹配（后端无关）
│   ├── targets.py            # 关键词定位唯一目标（--query 一次调用，0/多命中停下）
│   ├── attendees.py          # 与会人增删纯函数（校验 / 去重 / 显示）
│   ├── contacts.py           # 通讯录：姓名 → 邮箱（确定性解析，查不到就报错）
│   ├── notices.py            # 写操作后的事后提醒（冲突、会议室响应状态）
│   ├── google_auth.py        # Google OAuth（过渡期保留）
│   ├── calendar_service.py   # Google Calendar 封装（过渡期保留）
│   └── datetime_utils.py     # timezone-aware 日期时间工具
├── scripts/
│   ├── list_events.py        # 查询日程
│   ├── create_event.py       # 创建日程
│   ├── find_free_time.py     # 查找空闲时间
│   ├── search_events.py      # 搜索日程（只查不改）
│   ├── update_event.py       # 修改日程（默认执行，--dry-run 预览）
│   ├── delete_event.py       # 删除日程（默认执行，--dry-run 预览）
│   ├── list_rooms.py         # 会议室清单与占用
│   ├── contacts.py           # 通讯录查询（姓名 ↔ 邮箱）
│   └── register_outlook_app.py # 应用注册引导（门户被租户限制时的一次性工具）
└── tests/
    ├── test_datetime_utils.py
    ├── test_free_time.py
    ├── test_create_event.py
    ├── test_conflicts.py
    ├── test_event_match.py
    ├── test_update_delete.py
    ├── test_attendees.py
    ├── test_contacts.py
    ├── test_targets.py
    ├── test_notices.py
    ├── test_ics_parsing.py
    ├── test_outlook_cloud.py
    ├── test_outlook_parsing.py
    └── test_rooms.py
```

## 推送到 GitHub

远端 `origin` 是指向私有仓库 https://github.com/RoyWong-gogogo/Calendar-Assist 的 SSH 地址（`git@github.com:RoyWong-gogogo/Calendar-Assist.git`），本机 SSH 密钥已验证可用（`ssh -T git@github.com` 返回 `Hi RoyWong-gogogo!`）。日常推送一条命令：

```powershell
git push
```

本机已装 GitHub CLI（`gh`；安装命令 `winget install --id GitHub.cli -e`）并完成过一次设备码授权，token 存在 Windows 凭据管理器（keyring），`git_protocol=ssh`。换机器或凭据失效时重新授权：

```powershell
gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
```

终端会打印一次性代码（形如 `9A18-26F0`）和地址 https://github.com/login/device ，在浏览器输入代码后点 Authorize 即可，授权完成后终端显示 `Logged in as RoyWong-gogogo`。为避免自动弹窗，上面用 `GH_BROWSER=echo` 让 gh 只打印地址、由用户手动打开；若希望自动弹出浏览器，去掉该环境变量即可。

首次建仓用的是 `gh repo create Calendar-Assist --private --source . --remote origin --push`，仓库已存在时不要重复执行。

注意：仓库含 `data/contacts.csv`（同事与外部联系人邮箱），保持私有；改成公开前必须先征得用户同意。

## 安全注意

以下内容**绝不能提交 Git**（`.gitignore` 已排除）：

- `credentials/` 中的所有凭证与 token（`outlook_token.bin`、`credentials.json`、`token.json`）
- `.env`
- `.venv/`

## 开发计划

- Session 1：项目骨架 + OAuth + `list_events`（已完成；历经 Google → Outlook 全球端点 → 世纪互联中国区端点的摸索，最终落在中国区 Graph）
- Session 2：`create_event` + `find_free_time`（已完成，基于中国区 Graph 读写）
- Session 3：`update_event` + `delete_event` + 事件搜索匹配 + 冲突检查（已完成，全部基于 mock 测试）
- **当前建议：真实使用一到两周**，记录不顺手的细节（"下午"的边界、默认时长、默认提醒等），作为下一阶段的输入
- Session 4：会议室（CDConfRoom）查询与预订：`scripts/list_rooms.py` + `create_event --room` / `update_event --room`（已完成）
- Session 5：流程提速（已完成）：`--query` 一次调用定位并执行、默认执行（`--dry-run` 预览）、冲突与会议室忙闲改为事后提醒
- Session 6：与会人邀请（已完成）：`create_event --attendee` / `update_event --attendee` / `--remove-attendee`（`src/attendees.py`）
- Session 7：通讯录（已完成）：`data/contacts.csv`（姓名 ↔ 邮箱）+ `src/contacts.py` + `scripts/contacts.py`；`--attendee 姓名` 直接解析，查不到 / 命中多个都停下
- Session 8：推送到 GitHub（已完成）：`origin` 指向私有仓库 RoyWong-gogogo/Calendar-Assist，SSH 推送；本机安装 GitHub CLI 并完成设备码授权（token 存 Windows 凭据管理器）
- 之后候选：`find_free_time` 区分 showAs 空闲状态、清理 Google / ICS 备用后端

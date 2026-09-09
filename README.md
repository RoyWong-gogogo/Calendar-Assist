# calendar-agent

轻量级个人日程助手。**Codex 对话窗口就是交互入口**：直接用自然语言问日程、约会议、找空档，Codex 调用本项目中的工具读写 Google Calendar，并把结果告诉你。

**Google Calendar 是唯一日程事实源** —— 所有日程查询都实际读取 Google Calendar，不依赖聊天记录。

## 当前功能

| 能力 | 状态 |
| --- | --- |
| 查询日程 `list_events` | 已实现 |
| 创建日程 `create_event` | 计划 Session 2 |
| 查询空闲时间 `find_free_time` | 计划 Session 2 |

修改、删除日程暂不支持。

## 环境要求

- Windows + PowerShell
- Python 3.11+（开发环境为 3.14）
- 一个 Google 账号

## 安装

```powershell
py -3.14 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

也可以先激活虚拟环境再直接用 `python`：

```powershell
./.venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
```

## Google Cloud OAuth 配置（一次性，人工步骤）

1. **创建项目**：打开 <https://console.cloud.google.com/>，新建一个项目（或选用已有项目），例如命名为 `calendar-agent`。
2. **启用 API**：进入 "APIs & Services → Library"，搜索 **Google Calendar API** 并点击 Enable。直达链接：<https://console.cloud.google.com/apis/library/calendar.googleapis.com>。
3. **配置 OAuth 同意屏幕**：进入 "APIs & Services → OAuth consent screen"：
   - User Type 选 **External**
   - 应用名称随意（如 `calendar-agent`），其余保持默认
   - 在 **Test users** 中添加你自己的 Google 邮箱（必须，否则无法完成授权）
   - 保持 **Testing** 状态即可，不需要发布
4. **创建 OAuth 凭证**：进入 "APIs & Services → Credentials → Create Credentials → OAuth client ID"：
   - Application type 选 **Desktop app**
   - 名称随意（如 `calendar-agent`）
5. **下载 JSON**：创建完成后点击 "Download JSON"，保存到项目的 `credentials/` 目录，**文件名必须是 `credentials.json`**（完整路径：`credentials/credentials.json`）。

## 首次授权与验证

```powershell
./.venv/Scripts/python.exe scripts/list_events.py
```

首次运行会自动打开浏览器完成 Google 授权。因为应用处于 Testing 状态，Google 可能提示“未经验证的应用”，点 **高级 → 继续前往**，选择你的账号并允许即可。授权成功后 token 会缓存到 `credentials/token.json`，之后无需重复登录。

命令会输出你今天的真实日程，证明 Python → Google Calendar API 的链路已经打通。

> 授权范围说明：本项目申请的是 `https://www.googleapis.com/auth/calendar.events`（日程读写权限）。当前只用到读取，但为了后续实现创建日程时不需要重新授权，一开始就申请了读写范围。

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
| `CALENDAR_TIMEZONE` | `Asia/Shanghai` | 解析日期时间的默认时区（IANA 名称） |
| `GOOGLE_CALENDAR_ID` | `primary` | 操作的日历，`primary` 即主日历 |
| `GOOGLE_CREDENTIALS_FILE` | `credentials/credentials.json` | OAuth 客户端 JSON 路径 |
| `GOOGLE_TOKEN_FILE` | `credentials/token.json` | 缓存 token 路径 |

## 项目结构

```
├── AGENTS.md               # Codex 工作守则（新 Session 必读）
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── credentials/            # OAuth 凭证与 token（不提交 Git）
│   └── README.md
├── src/
│   ├── config.py           # 配置：时区、路径、日历 ID
│   ├── google_auth.py      # Google OAuth（与业务代码分离）
│   ├── datetime_utils.py   # timezone-aware 日期时间工具
│   └── calendar_service.py # Google Calendar API 封装
├── scripts/
│   └── list_events.py      # 查询日程
└── tests/
    └── test_datetime_utils.py
```

## 安全注意

以下内容**绝不能提交 Git**（`.gitignore` 已排除）：

- `credentials/` 中的 `credentials.json`（OAuth 客户端密钥）与 `token.json`（缓存 token）
- `.env`
- `.venv/`

## 开发计划

- Session 1：项目骨架 + OAuth + `list_events` 读取真实日历
- Session 2：`create_event` + `find_free_time`
- 之后：按需评估修改、删除日程

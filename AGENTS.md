# AGENTS.md — calendar-agent 项目守则

## 项目定位

calendar-agent 是一个轻量级的个人日程助手。**Codex 对话窗口本身就是用户入口**：用户直接用自然语言提出日程需求（例如“今天有什么安排”“下周三上午有空吗”“明天下午 3 点安排一个会议”），Codex 负责理解意图、换算时间、调用本项目中的工具，再把结果整理成自然语言回复。

本项目不开发独立聊天程序、Web UI、桌面 App 或其他任何界面。

## 日历后端

当前主后端是 **Outlook Calendar（中国区 Microsoft Graph OAuth）**：工作邮箱是世纪互联运营的 Microsoft 365（partner.outlook.cn），必须走中国区端点——门户 portal.azure.cn、登录 login.partner.microsoftonline.cn、API microsoftgraph.chinacloudapi.cn。端点由 `.env` 的 `OUTLOOK_CLOUD=china` 控制（`src/config.py` 内置 china / global 两套映射），`CALENDAR_PROVIDER=outlook`。

ICS 订阅链接后端（`src/ics_service.py`，`CALENDAR_PROVIDER=ics`）作为**只读后备**：无需 OAuth，但只能查询；数据是发布快照（非实时，有延迟）；`ICS_URL` 是机密凭证（等同密码，只放 `.env`）。

Google 实现（`src/google_auth.py` / `src/calendar_service.py`，`CALENDAR_PROVIDER=google`）仅保留代码，全球 OAuth 无法登录，暂不可用。

后端由 `src/config.py` 的 `CALENDAR_PROVIDER` 控制，通过 `src/service_factory.py` 选择具体实现；各后端的 `list_events` 返回结构完全一致。

## 不可违反的原则

1. **当前配置的日历服务（默认 Outlook 中国区 Graph）是唯一日程事实源。** 任何涉及“现在有什么日程”“某段时间是否有空”的回答，都必须实际调用日历 API 读取数据，禁止凭聊天记录、上下文或记忆猜测日程。
2. **不要在没有验证日历 API 返回结果的情况下，声称某个日程存在或不存在。** 结论必须基于 API 实际返回的数据。
3. **所有 datetime 必须 timezone-aware。** 禁止用 naive datetime 调用日历 API。默认时区只在 `src/config.py` 定义一处（初始值 `Asia/Shanghai`），不要在其他文件硬编码时区。内部时间统一使用 ISO 8601。
4. **相对日期（今天 / 明天 / 后天 / 本周五 / 下周三 / 上午 / 下午 / 晚上）**由 Codex 先基于当前本地日期和配置时区换算成明确时间，再调用工具。项目内不需要也不应该引入自然语言解析器或额外的 LLM 调用。
5. **不要引入复杂框架。** 不使用 LangChain、LangGraph、向量数据库、本地日程数据库、多 Agent、MCP Server、独立 LLM API、语音识别。技术栈保持为 Python + 日历 API + 标准库 + 少量必要第三方依赖。
6. **代码优先简单、可读、易调试、易扩展。** 避免过度封装，不为“架构完整”增加当前阶段不需要的层。
7. **所有日历 API 错误都要给出明确异常信息，不要吞掉错误。**
8. **Outlook OAuth 使用设备代码流**：首次授权需要用户在浏览器打开 https://microsoft.com/devicelogin 并输入一次性代码。Codex 运行授权相关命令时，必须把代码和操作步骤清楚转达给用户，并等用户完成后再继续；不要在用户未完成授权时反复重试。

## 当前功能范围

v0.1 的三个核心能力（均已实现）：

- 查询日程 `list_events` — 已实现（ICS / Outlook / Google 多后端）
- 创建日程 `create_event` — 已实现（仅 Outlook 后端；ICS 只读 / Google 不可用，调用会明确报错）
- 查询空闲时间 `find_free_time` — 已实现（全部后端；v0.1 将日历上所有事件视为忙碌，不区分 Graph showAs 空闲状态）
- 修改日程 `update_event` — 已实现（仅 Outlook 后端；`scripts/update_event.py`）
- 删除日程 `delete_event` — 已实现（仅 Outlook 后端；`scripts/delete_event.py`）
- 事件搜索 `search_events` — 已实现（时间范围 + 关键词的确定性匹配；`scripts/search_events.py`）
- 会议室查询 `list_rooms` — 已实现（仅 Outlook 后端；中国区 Graph 无会议室清单接口，按会议室邮箱命名规律扫描编号区间；`scripts/list_rooms.py`）
- 会议室预订 — 已实现（`create_event --room` / `update_event --room`，会议室以 **resource 与会人** 写入事件）

**暂不实现**：修改 / 删除日程的批量操作、独立聊天程序、Web UI、App、React、LangChain、LangGraph、向量数据库、本地日程数据库、多 Agent、MCP Server、独立 LLM API、Whisper / 语音识别。

未经用户明确要求，不要主动实现“暂不实现”清单中的功能。

## 安全

- `credentials/` 目录下的所有文件（Outlook 的 `outlook_token.bin`，Google 的 `credentials.json` / `token.json`）**绝不能提交 Git**。
- `.env` 不能提交 Git；其中 ICS 订阅链接 `ICS_URL` 等同凭证，任何拿到的人都能查看日历。
- 不要在代码、README、日志或对话中输出任何 OAuth secret。
- 不要用用户的真实日历做破坏性测试（创建 / 修改 / 删除事件），除非用户明确要求并确认。

## 开发环境

- Windows + PowerShell，Python 3.11+（当前 3.14），虚拟环境位于 `.venv/`。
- 常用命令（项目根目录）：

```powershell
./.venv/Scripts/Activate.ps1
python scripts/list_events.py                      # 查询今天
python scripts/list_events.py --date 2026-09-10    # 查询指定日期
python scripts/list_events.py --from 2026-09-10T09:00 --to 2026-09-10T18:00
python scripts/list_events.py --json               # JSON 输出（便于程序读取）
python scripts/create_event.py --title "和王总开会" --start 2026-09-14T15:00 --duration 60
python scripts/find_free_time.py --from 2026-09-14T09:00 --to 2026-09-14T18:00 --duration 60
python scripts/search_events.py --date 2026-09-14 --query 雅江
python scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60          # 预览
python scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60 --yes    # 执行
python scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801
python scripts/list_rooms.py --date 2026-09-15     # 会议室清单与占用（扫描编号 800-850）
python scripts/update_event.py --event-id <id> --room 803 --yes    # 改会议室（--room "" 取消）
python scripts/delete_event.py --event-id <id>          # 预览
python scripts/delete_event.py --event-id <id> --yes    # 执行
python -m unittest discover -s tests -v            # 运行测试
```

## 工作方式

当用户说“我明天下午有什么安排”时：先把“明天下午”换算成准确的时间范围，然后调用 `scripts/list_events.py`（或 `service_factory.get_calendar_service_class()`）实际读取日历，最后用简洁的自然语言汇报结果。禁止凭上下文猜测日历内容。

当用户说“明天下午 3 点和王总开会一个小时”时：先换算成明确时间，必要时先查询该时段是否已有安排，然后调用 `scripts/create_event.py` 写入日历，并汇报创建结果（id、时间、标题）。

当用户说“下周三下午帮我找一个小时空档”时：先换算时间范围，调用 `scripts/find_free_time.py`，把可选时段用自然语言汇报，让用户挑选。

## 修改与删除日程的规则（安全机制）

当用户说“把明天下午和壁仞的会议改到四点”或“取消周五那个客户会议”时，**不得直接操作**，必须走：

1. 根据用户描述换算搜索时间范围（宁大勿小，如“明天下午”= 明天 12:00–18:00）
2. 调用 `scripts/search_events.py` **实际读取日历**并按关键词过滤候选
3. 没有匹配：明确告知没找到，不得构造 event id，也不得创建新事件顶替修改
4. 多个候选：**列出候选让用户选择，禁止猜测**
5. 唯一匹配：向用户展示目标（原日程 → 新日程 / 待删除日程）并确认
6. 用户确认后：先跑**不带 --yes 的预览**看冲突提示，再带 `--yes` 执行
7. 操作必须通过真实 event id；禁止仅凭标题删除或修改

**冲突检查**：`update_event.py` 在时间变化时自动查询新时段的已有日程（排除自身 event id）并显示冲突；存在冲突时明确告知用户冲突事件，由用户决定是否仍加 `--yes` 继续。`create_event` 目前不做自动冲突检查，Codex 在创建前应先查询目标时段（发现冲突时提醒用户，是否创建由用户决定）。

**重复日程**：遇到重复日程（instance / series master）时，修改和删除前必须向用户说明影响范围（“仅这一场”或“整个系列”），语义不明确时先让用户选择，不得因实现方便而擅自操作整个系列。脚本会对重复日程打印 ⚠️ 提示。

## 会议室（CDConfRoom）

- 会议室是 Exchange **room mailbox**（资源邮箱，`CDConfRoomNNN@arraycomm.com`），和“地点文本”不是一回事：只有把会议室作为 **resource 与会人** 写入事件（`--room`）才算真正预订；只写 `--location` 只是标签，不会占用会议室。
- 中国区 Graph 没有可用的会议室清单接口（`/me/findRooms` 缺委托权限返回 403、`/places` 返回 403、`/me/findMeetingTimes` 返回 405，2026-09 实测），因此用 `scripts/list_rooms.py` 按「前缀 + 编号 @ 域名」扫描编号区间，并用 `getSchedule` 确认邮箱是否存在、忙闲如何。前缀 / 域名见 `src/config.py` 的 `ROOM_NAME_PREFIX` / `ROOM_EMAIL_DOMAIN`。
- 预订前必须先查会议室忙闲（脚本已内置）：会议室在目标时段被占用时，`create_event --room` 会打印 `[会议室占用]` 并**停止创建**（退出码 3；只有用户确认强行创建才加 `--force-room`）；`update_event --room` 会在预览里打印 ⚠️ 并停止（退出码 3；用户确认才加 `--yes`）。
- 改 / 取消会议室同样走 search → 匹配 → 展示 → 确认 → `update_event --room`（`--room ""` 取消）；会议室是否自动接受邀请由 Exchange 策略决定，脚本只负责发出邀请。
- 本租户实测：会议室会自动接受邀请（事件与会人 `status.response = accepted`）；但**跨邮箱忙闲缓存有延迟**，刚订完的几分钟内 `list_rooms` / `getSchedule` 可能仍显示该会议室空闲——判断是否订上要看事件的会议室与会人响应状态，不要仅凭忙闲视图下结论。

## 执行约定（Codex 自用）

- **写操作先看权限**：本机沙箱里 `.git` 是只读的，`git commit` 必然需要授权——直接带升级请求执行，不要先在沙箱内试一次、被拒后再重发。
- **不做无结论价值的等待**：已有权威信号时不要 sleep 轮询次要信号（例：会议室忙闲缓存有延迟，但与会人 `accepted` 已是最终答案），避免让用户对着空屏等。
- **收尾从简**：动作完成 + 一次必要回读即可，不再追加可做可不做的检查（提交后的重复 `git status`、被删事件后的再确认等）。
- **汇报顺序**：先给结果，再简述过程与限制；总结保持短，长分析只放在用户明确追问时。

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
- 邀请与会人 — 已实现（`create_event --attendee` / `update_event --attendee` / `--remove-attendee`，以 required 类型与会人发出邀请）
- 通讯录 `contacts` — 已实现（只读；`data/contacts.csv` 是「姓名 → 邮箱」的唯一事实源，邀请时 `--attendee` 可直接写姓名；`src/contacts.py` / `scripts/contacts.py`）

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
python scripts/update_event.py --query 壁仞 --date tomorrow --start 2026-09-14T16:00 --duration 60  # 一条命令定位并改
python scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60             # 直接执行
python scripts/update_event.py --event-id <id> --start 2026-09-14T16:00 --duration 60 --dry-run   # 只看不改
python scripts/create_event.py --title "投资人访谈" --start 2026-09-15T10:00 --duration 60 --room 801
python scripts/list_rooms.py --date 2026-09-15     # 会议室清单与占用（扫描编号 800-850）
python scripts/contacts.py --query nanqing         # 通讯录模糊查（姓名 → 邮箱）
python scripts/contacts.py --name "Nanqing Zhou"   # 精确解析，输出邮箱（邀请时可直接写姓名）
python scripts/contacts.py --list --external       # 列出全部 / 只看外部联系人
python scripts/update_event.py --event-id <id> --room 803             # 改会议室（--room "" 取消）
python scripts/update_event.py --event-id <id> --attendee a@arraycomm.com   # 邀请与会人（可重复传入）
python scripts/update_event.py --event-id <id> --remove-attendee a@arraycomm.com  # 移除与会人
python scripts/delete_event.py --event-id <id>                        # 直接删除
python scripts/delete_event.py --query 客户会议 --date tomorrow       # 一条命令定位并删
python -m unittest discover -s tests -v            # 运行测试
```

## 工作方式

当用户说“我明天下午有什么安排”时：先把“明天下午”换算成准确的时间范围，然后调用 `scripts/list_events.py`（或 `service_factory.get_calendar_service_class()`）实际读取日历，最后用简洁的自然语言汇报结果。禁止凭上下文猜测日历内容。

当用户说“明天下午 3 点和王总开会一个小时”时：先换算成明确时间，直接调用 `scripts/create_event.py` 写入日历（**默认不带 `--room`，不预订会议室**，除非用户明确要求），并汇报创建结果（id、时间、标题）。脚本在创建后会做一次事后提醒（该时段是否已有其它日程），把它一并汇报给用户。

当用户说“下周三下午帮我找一个小时空档”时：先换算时间范围，调用 `scripts/find_free_time.py`，把可选时段用自然语言汇报，让用户挑选。

## 修改与删除日程的规则

设计目标：**一条命令改完**。真实使用中的延迟主要来自「搜索 → 预览 → 确认 → 执行」四步，已按此简化。当用户说“把明天下午和壁仞的会议改到四点”或“取消周五那个客户会议”时：

1. **定位与写入合并成一条命令**：`--query 关键词` 配合 `--date` / `--from`+`--to`（宁大勿小，如“明天下午”= 明天 12:00–18:00），例如 `python scripts/update_event.py --query 壁仞 --date tomorrow --start 2026-09-14T16:00 --duration 60`；删除同理 `python scripts/delete_event.py --query 客户会议 --date tomorrow`。脚本自己读日历并按关键词过滤（见 `src/targets.py`）。
2. **恰好 1 个命中即视为已授权，直接执行**：默认就写，没有确认步骤（`--dry-run` 才是预览）。用户的明确指令 + 唯一命中就是授权。
3. **0 命中或 ≥2 个候选才停下**（退出码 4）：脚本会列出候选（含 event id）或明确说“没找到”。此时把结果转述给用户，让用户指定是哪一个或换关键词；**禁止猜测**，不得构造 event id，也不得创建新事件顶替修改。

底线不变：操作必须落在真实 event id 上；走 `--event-id`（沿用上次汇报里的 id）时同样默认直接执行。`search_events.py` 保留用于只查不改的搜索，`--yes` 保留为兼容空参数，不再影响行为。

**冲突改为事后提醒**：`update_event.py` / `create_event.py` 都不做事前冲突预检，写完读一次目标时段，把重叠的其它日程打印成 `[事后提醒]`。汇报时先给结果，再把提醒转述给用户（该时段还有哪些日程）；是否再调整由用户决定，写操作不因冲突阻塞。提醒读取失败不改退出码（写操作已成功）；`--no-notice` 可跳过这次读取。

**重复日程**：遇到重复日程（instance / series master）时，修改和删除前必须向用户说明影响范围（“仅这一场”或“整个系列”），语义不明确时先让用户选择，不得因实现方便而擅自操作整个系列。脚本会对重复日程打印 ⚠️ 提示；`--query` 命中的若是系列母事件，脚本会停下（退出码 4）并要求改用 `--event-id` 明确指定。

## 与会人邀请

- 与会人和会议室在事件里是**同一个 attendees 数组**：普通与会人（required / optional）与会议室（resource）。`--attendee` / `--remove-attendee` 只增删普通与会人，**不会动已订的会议室**；只有显式给 `--room` 才会替换 resource 条目（见 `src/attendees.py` 的 `split_people` / `merge`）。
- 邀请：`create_event --attendee 邮箱|姓名` 或 `update_event --attendee 邮箱|姓名`（可重复传入，required 类型）；移除：`update_event --remove-attendee 邮箱|姓名`。**姓名走通讯录 `data/contacts.csv` 解析**（`src/contacts.py`）：按姓名 / 别名 / 完整邮箱 / 邮箱本地部分比对，忽略大小写与空白（`Nanqing Zhou` = `nanqingzhou` = `nzhou`）；解析在发请求前完成，查不到或命中多个都直接报错（退出码 2，不猜地址，也不做任何网络请求），重复邀请按地址去重（大小写不敏感）。
- 写 attendees 时 Graph 按新数组整体覆盖：已有与会人会被重新提交，其响应状态可能被重置；这是 Exchange 的语义，不是脚本 bug。
- **不要凭姓名猜邮箱**：先查通讯录（`python scripts/contacts.py --query 关键词` 模糊找，或 `--name 姓名` 精确解析）；通讯录里没有就问用户，或扫历史日程的与会人（`list_events` 的 `attendees` 自带 name + address，取一段时间范围按姓名过滤，2026-09 实测有效），确认后再补进通讯录。中国区 Graph 没有可用的通讯录搜索（`/me/people` 的 `$search` 需 `property:value` 形式且实测返回 400）。
- **通讯录维护**：`data/contacts.csv` 是「姓名 → 邮箱」的唯一事实源，列 `name,address,aliases,note`（`aliases` 用 `;` 分隔多个写法；外部联系人 `note` 写「外部: 域名」）。初始条目来自历史日历（2025-09 ~ 2026-09）的与会人扫描：132 个内部地址 + 64 个外部地址，已排除会议室邮箱。新增联系人直接编辑 CSV；姓名有别的写法（英文名 / 中文名 / 拼音）就填进 `aliases`，下次才解析得出来。
- 邀请结果看事件里各与会人的响应状态：`accepted` / `tentativelyAccepted` / `declined` / `none`（刚发出时都是 `none`，对方操作后才变）；`update_event.py` 写完会把与会人连同响应状态打印出来，照此汇报即可。

## 会议室（CDConfRoom）

- **默认不预订会议室**：用户没有明确要求会议室时，创建 / 修改日程一律**不带 `--room`**；只有用户明确说要订会议室（给出编号，或授权你挑选）时才预订。拿不准就先问，不要默认占房。
- 会议室是 Exchange **room mailbox**（资源邮箱，`CDConfRoomNNN@arraycomm.com`），和“地点文本”不是一回事：只有把会议室作为 **resource 与会人** 写入事件（`--room`）才算真正预订；只写 `--location` 只是标签，不会占用会议室。
- 中国区 Graph 没有可用的会议室清单接口（`/me/findRooms` 缺委托权限返回 403、`/places` 返回 403、`/me/findMeetingTimes` 返回 405，2026-09 实测），因此用 `scripts/list_rooms.py` 按「前缀 + 编号 @ 域名」扫描编号区间，并用 `getSchedule` 确认邮箱是否存在、忙闲如何。前缀 / 域名见 `src/config.py` 的 `ROOM_NAME_PREFIX` / `ROOM_EMAIL_DOMAIN`。
- **预订不做事前忙闲预检**（每次 `getSchedule` 都要一次额外往返，且跨邮箱忙闲缓存本身有延迟、不可靠）：`create_event --room` / `update_event --room` 直接发出邀请，**以写完后事件里该会议室与会人的 `status.response` 判定结果**——`accepted` 已订上；`none` / 未响应则稍后再确认；`declined` 说明房间拒绝（被占用或不可预订），需换一间。给用户挑会议室时仍用 `scripts/list_rooms.py`（一次扫描整个区间，比逐间预检划算）。`--force-room` / `--yes` 保留为兼容空参数，不再影响行为。
- 改 / 取消会议室同样走 `--query` / `--event-id` + `update_event --room`（`--room ""` 取消）；会议室是否自动接受邀请由 Exchange 策略决定，脚本只负责发出邀请。
- 本租户实测：会议室会自动接受邀请（事件与会人 `status.response = accepted`）；但**跨邮箱忙闲缓存有延迟**，刚订完的几分钟内 `list_rooms` / `getSchedule` 可能仍显示该会议室空闲——判断是否订上要看事件的会议室与会人响应状态，不要仅凭忙闲视图下结论。

## 执行约定（Codex 自用）

- **写操作先看权限**：本机沙箱里 `.git` 是只读的，`git commit` 必然需要授权——直接带升级请求执行，不要先在沙箱内试一次、被拒后再重发。
- **不做无结论价值的等待**：已有权威信号时不要 sleep 轮询次要信号（例：会议室忙闲缓存有延迟，但与会人 `accepted` 已是最终答案），避免让用户对着空屏等。
- **收尾从简**：动作完成 + 一次必要回读即可，不再追加可做可不做的检查（提交后的重复 `git status`、被删事件后的再确认等）。
- **汇报顺序**：先给结果，再简述过程与限制；总结保持短，长分析只放在用户明确追问时。
- **日历脚本要联网**：本机沙箱默认拦截网络，日历脚本访问 Graph 需要升级授权——直接在升级请求里执行（或按已登记的 prefix rule 运行），不要为了省授权去改代码或换数据源。
- **推送走 SSH + gh**：`origin` 已指向私有仓库 `git@github.com:RoyWong-gogogo/Calendar-Assist.git`，提交后直接 `git push`（写 .git 需要升级授权）。`gh` 已完成设备码授权（token 存 Windows 凭据管理器，`git_protocol=ssh`）；需要重新授权时执行 `gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web`，把一次性代码与 https://github.com/login/device 清楚转达用户并等其完成。仓库含 `data/contacts.csv` 中的同事邮箱，保持私有，改公开前必须征得用户同意。

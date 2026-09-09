# AGENTS.md — calendar-agent 项目守则

## 项目定位

calendar-agent 是一个轻量级的个人日程助手。**Codex 对话窗口本身就是用户入口**：用户直接用自然语言提出日程需求（例如“今天有什么安排”“下周三上午有空吗”“明天下午 3 点安排一个会议”），Codex 负责理解意图、换算时间、调用本项目中的工具，再把结果整理成自然语言回复。

本项目不开发独立聊天程序、Web UI、桌面 App 或其他任何界面。

## 日历后端

当前默认接入 **Outlook Calendar（Microsoft Graph API）**（用户的 Google Calendar 无法完成登录，已切换到微软体系）。Google 实现过渡期保留在 `src/google_auth.py` / `src/calendar_service.py`，可通过 `CALENDAR_PROVIDER=google` 切换；**Outlook 验证通过后将删除 Google 实现**。

后端由 `src/config.py` 的 `CALENDAR_PROVIDER` 控制（默认 `outlook`），通过 `src/service_factory.py` 选择具体实现；两个后端的 `list_events` 返回结构完全一致。

## 不可违反的原则

1. **当前配置的日历服务（默认 Outlook Calendar）是唯一日程事实源。** 任何涉及“现在有什么日程”“某段时间是否有空”的回答，都必须实际调用日历 API 读取数据，禁止凭聊天记录、上下文或记忆猜测日程。
2. **不要在没有验证日历 API 返回结果的情况下，声称某个日程存在或不存在。** 结论必须基于 API 实际返回的数据。
3. **所有 datetime 必须 timezone-aware。** 禁止用 naive datetime 调用日历 API。默认时区只在 `src/config.py` 定义一处（初始值 `Asia/Shanghai`），不要在其他文件硬编码时区。内部时间统一使用 ISO 8601。
4. **相对日期（今天 / 明天 / 后天 / 本周五 / 下周三 / 上午 / 下午 / 晚上）**由 Codex 先基于当前本地日期和配置时区换算成明确时间，再调用工具。项目内不需要也不应该引入自然语言解析器或额外的 LLM 调用。
5. **不要引入复杂框架。** 不使用 LangChain、LangGraph、向量数据库、本地日程数据库、多 Agent、MCP Server、独立 LLM API、语音识别。技术栈保持为 Python + 日历 API + 标准库 + 少量必要第三方依赖。
6. **代码优先简单、可读、易调试、易扩展。** 避免过度封装，不为“架构完整”增加当前阶段不需要的层。
7. **所有日历 API 错误都要给出明确异常信息，不要吞掉错误。**
8. **Outlook OAuth 默认使用设备代码流**：首次授权需要用户在浏览器打开 https://microsoft.com/devicelogin 并输入一次性代码。Codex 运行授权相关命令时，必须把代码和操作步骤清楚转达给用户，并等用户完成后再继续；不要在用户未完成授权时反复重试。

## 当前功能范围

v0.1 只计划支持以下三个能力：

- 查询日程 `list_events` — 已实现（Outlook + Google 双后端）
- 创建日程 `create_event` — 计划中（Session 2）
- 查询空闲时间 `find_free_time` — 计划中（Session 2）

**暂不实现**：修改日程、删除日程、独立聊天程序、Web UI、App、React、LangChain、LangGraph、向量数据库、本地日程数据库、多 Agent、MCP Server、独立 LLM API、Whisper / 语音识别。

未经用户明确要求，不要主动实现“暂不实现”清单中的功能，也不要提前实现“计划中”的功能。

## 安全

- `credentials/` 目录下的所有文件（Outlook 的 `outlook_token.bin`，Google 的 `credentials.json` / `token.json`）**绝不能提交 Git**。
- `.env` 不能提交 Git。
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
python -m unittest discover -s tests -v            # 运行测试
```

## 工作方式

当用户说“我明天下午有什么安排”时：先把“明天下午”换算成准确的时间范围，然后调用 `scripts/list_events.py`（或 `service_factory.get_calendar_service_class()`）实际读取日历，最后用简洁的自然语言汇报结果。禁止凭上下文猜测日历内容。

# TeamFlow AI 完成状态

本文档记录当前真实实现状态，作为后续开发入口。更详细的设计说明见 `DESIGN.md`，使用方式见 `USAGE.md`。

## 已完成

- 本地环境依赖已补齐，`python -m pip check` 通过。
- 测试环境已补齐 `pytest` / `pytest-asyncio`，当前测试通过。
- FastAPI 服务包含 `/health` 与 `/health/detailed`。
- `/api/*` 已接入 API Key 校验；本机请求和 webhook 路由保持豁免。
- DecisionEngine 已接入规则、策略、LLM fallback 三层决策。
- 核心 Action 已注册：通知、文档、邮件、任务、日历、审批、观察日志、重分配建议。
- 调度器支持 Git 扫描、逾期扫描、停滞任务扫描、健康检查、周报、里程碑扫描、策略维护等任务。
- SQLite 使用 WAL 模式，包含项目、成员、任务、依赖、里程碑、观察、决策、会话等表。
- 飞书核心闭环具备 mock 可测能力：通知、任务同步、审批、日程。
- 用户可见的规则模板与 LLM prompt 已修复为可读中文。

## 后续增强

- 真正的“隔离子代理”尚未实现；当前 `sub_agent` 是并发项目巡检器。
- 富媒体消息、交互卡片、复杂飞书审批表单属于后续增强。
- 真实飞书凭证联调仍需在目标租户中执行 `teamflow doctor` 和手动 smoke test。
- 策略自进化当前支持记录、降级和归档；自动改写策略内容可以后续增强。
- 可进一步补充端到端启动测试和真实 CLI 命令测试。

## 验证命令

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m pytest tests/ -q
python run.py
```

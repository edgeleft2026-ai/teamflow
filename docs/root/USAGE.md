# TeamFlow AI 使用说明

TeamFlow AI 是一个 AI 驱动的项目管理助手。它通过“感知 → 决策 → 行动”的循环监控项目状态，发现风险，并通过飞书执行通知、任务同步、审批和日程等协作动作。

## 快速开始

```bash
python -m pip install -r requirements.txt
python run.py
```

服务启动后访问：

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`
- 详细健康检查：`http://localhost:8000/health/detailed`

也可以安装 CLI：

```bash
python -m pip install -e ".[test]"
teamflow setup
teamflow doctor
teamflow run --port 8000
```

## 配置

默认配置位于 `config/default.yaml`，用户配置位于 `~/.teamflow/config.yaml`，支持 `${ENV:default}` 模板。

常用环境变量：

```env
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=xxx
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
TEAMFLOW_API_KEY=tf_xxx
```

配置文件顶层包含 `_config_version: 1`。旧配置会在加载时自动补齐版本号。

## API 认证

`/api/*` 默认接入 API Key 校验：

- Header：`X-API-Key: tf_xxx`
- 或：`Authorization: Bearer tf_xxx`
- 本机请求自动放行。
- `/api/webhooks/*` 自动放行，用于飞书回调。
- 如果没有设置 `TEAMFLOW_API_KEY` 且没有创建任何 key，开发环境默认放行。

## 核心接口

- `GET /api/status`：系统概览。
- `POST /api/projects`：创建项目。
- `GET /api/projects`：列出项目。
- `POST /api/projects/{id}/tasks`：创建任务。
- `PATCH /api/projects/{id}/tasks/{task_id}`：更新任务。
- `GET /api/projects/{id}/health`：项目健康度。
- `POST /api/projects/{id}/tasks/sync`：同步飞书任务。
- `POST /api/projects/{id}/calendar/event`：创建日程。
- `GET /api/strategies`：列出策略。
- `POST /api/strategies/archive-stale`：归档过期策略。
- `GET /api/credentials/status`：查看凭据池状态。
- `GET /api/sub-agents/status`：查看并发巡检器状态。

## 决策闭环

事件来源包括任务监控、Git 监控、调度器、API 和飞书回调。事件进入 EventBus 后由 AIAgent 处理，DecisionEngine 按以下顺序决策：

1. `config/rules.yaml` 中的确定性规则。
2. `strategies/active/*.md` 中的策略。
3. LLM fallback 分析未覆盖场景。

可用 Action 名称：

```text
notify, notify_assignee, notify_team, notify_admin,
feishu_doc, feishu_mail, feishu_task, feishu_calendar, feishu_approval,
log_observation, suggest_reassignment
```

## 调度任务

默认调度任务包括：

- `daily_standup`
- `overdue_scan`
- `git_activity_scan`
- `health_check`
- `weekly_report`
- `milestone_scan`
- `stale_task_scan`
- `branch_cleanup_check`
- `health_score`
- `multi_project_patrol`
- `strategy_maintenance`
- `approval_timeout_check`

## 测试

```bash
python -m pip check
python -m pytest tests/ -q
```

测试使用 mock，不需要真实飞书凭证。

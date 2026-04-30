# TeamFlow 数据与事件模型

## 1. 文档目的

本文定义 TeamFlow 第一阶段开发所需的核心数据对象、状态、事件 payload 和幂等规则。具体表结构可以按技术选型调整，但字段语义应保持一致。

## 2. 数据原则

1. 所有关键业务对象必须有稳定 ID。
2. 所有外部动作结果必须可回查。
3. 所有事件必须具备幂等键。
4. 所有用户身份统一使用飞书 open_id 作为第一阶段主标识。
5. 密钥、访问令牌和模型凭证不得写入业务表或日志。

## 3. 核心对象

### 3.1 Project

用于承载项目基础信息和飞书资源绑定。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 项目 ID，系统生成 |
| name | string | 是 | 项目名称 |
| git_repo_path | string | 是 | Git 仓库地址或本地路径 |
| admin_open_id | string | 是 | 项目管理员飞书 open_id |
| status | enum | 是 | 项目状态 |
| feishu_group_id | string | 否 | 飞书群 ID |
| feishu_group_link | string | 否 | 飞书群链接 |
| feishu_doc_url | string | 否 | 项目文档 URL |
| workspace_status | enum | 是 | 协作空间初始化状态 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

推荐唯一约束：

1. `id` 唯一。
2. 同一管理员下 `name` 可提示重复，但第一阶段不强制唯一。

### 3.2 Project.status

1. `creating`：创建中。
2. `created`：项目记录已创建。
3. `initializing_workspace`：协作空间初始化中。
4. `active`：项目可运行。
5. `failed`：项目创建失败。
6. `archived`：项目归档，第一阶段只保留状态，不建设归档流程。

### 3.3 workspace_status

1. `pending`：等待初始化。
2. `running`：初始化中。
3. `succeeded`：初始化成功。
4. `partial_failed`：部分步骤失败。
5. `failed`：初始化失败。

### 3.4 Member

用于承载项目成员身份和角色。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 成员记录 ID |
| project_id | string | 是 | 所属项目 |
| open_id | string | 是 | 飞书 open_id |
| display_name | string | 否 | 展示名 |
| role | enum | 是 | 项目角色 |
| status | enum | 是 | 成员状态 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

`role` 值：

1. `admin`
2. `owner`
3. `member`
4. `viewer`

### 3.5 Task

用于承载项目内需要跟踪的工作项。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 任务 ID |
| project_id | string | 是 | 所属项目 |
| title | string | 是 | 任务标题 |
| assignee_open_id | string | 否 | 负责人 open_id |
| status | enum | 是 | 任务状态 |
| due_at | datetime | 否 | 截止时间 |
| blocked_reason | string | 否 | 阻塞原因 |
| last_activity_at | datetime | 否 | 最近活动时间 |
| source | enum | 是 | 数据来源 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

`status` 值：

1. `todo`
2. `in_progress`
3. `blocked`
4. `done`
5. `cancelled`

`source` 值：

1. `manual`
2. `git`
3. `feishu`
4. `imported`

### 3.6 ConversationState

用于持久化文本式创建流程。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 会话状态 ID |
| open_id | string | 是 | 用户 open_id |
| chat_id | string | 是 | 飞书会话 ID |
| flow | string | 是 | 流程名，例如 `create_project` |
| state | string | 是 | 当前状态 |
| payload | json | 是 | 已收集信息 |
| expires_at | datetime | 是 | 过期时间 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

创建项目推荐状态：

1. `idle`
2. `collecting_project_name`
3. `collecting_repo`
4. `creating_project`
5. `created`
6. `failed`

### 3.7 ProjectFormSubmission

用于持久化卡片表单创建流程的提交记录和进度追踪。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 记录 ID |
| request_id | string | 是 | 卡片回调 request_id（唯一，用于去重） |
| open_id | string | 是 | 提交用户 open_id |
| chat_id | string | 是 | 飞书会话 ID |
| open_message_id | string | 是 | 卡片消息 ID（用于更新进度卡片） |
| project_name | string | 是 | 项目名称 |
| git_repo_path | string | 是 | Git 仓库地址或本地路径 |
| status | enum | 是 | 提交处理状态 |
| current_step | string | 是 | 当前步骤描述 |
| steps_payload | json | 是 | 各步骤执行结果 |
| project_id | string | 否 | 关联项目 ID（创建成功后填入） |
| error_message | string | 否 | 错误信息 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

`status` 值：

1. `pending`：表单已提交，等待处理。
2. `creating_project`：项目创建中。
3. `initializing_workspace`：协作空间初始化中。
4. `succeeded`：全部完成。
5. `partial_failed`：部分步骤失败。
6. `failed`：处理失败。

推荐唯一约束：

1. `request_id` 唯一（防止重复表单提交）。

### 3.8 EventLog

用于记录业务事件和处理状态。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 事件记录 ID |
| event_type | string | 是 | 事件类型 |
| idempotency_key | string | 是 | 幂等键 |
| project_id | string | 否 | 关联项目 |
| source | string | 是 | 事件来源 |
| payload | json | 是 | 事件内容 |
| status | enum | 是 | 处理状态 |
| error_message | string | 否 | 错误信息 |
| created_at | datetime | 是 | 创建时间 |
| processed_at | datetime | 否 | 处理时间 |

`status` 值：

1. `pending`
2. `processing`
3. `succeeded`
4. `failed`
5. `ignored`

### 3.9 ActionLog

用于记录外部动作执行结果。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 动作记录 ID |
| project_id | string | 否 | 关联项目 |
| event_id | string | 否 | 关联事件 |
| action_name | string | 是 | 动作名称 |
| target | string | 否 | 动作目标 |
| input_summary | json | 是 | 脱敏后的输入摘要 |
| result | enum | 是 | 执行结果 |
| output_summary | json | 否 | 脱敏后的输出摘要 |
| error_message | string | 否 | 错误信息 |
| created_at | datetime | 是 | 创建时间 |
| finished_at | datetime | 否 | 完成时间 |

### 3.10 Observation

用于记录扫描、提醒和报告结果。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 观察记录 ID |
| project_id | string | 是 | 关联项目 |
| type | enum | 是 | 观察类型 |
| severity | enum | 是 | 严重程度 |
| title | string | 是 | 标题 |
| content | text | 是 | 内容 |
| evidence | json | 否 | 数据依据 |
| dedupe_key | string | 否 | 去重键 |
| created_at | datetime | 是 | 创建时间 |

`type` 值：

1. `overdue_task`
2. `blocked_task`
3. `stale_task`
4. `member_overload`
5. `daily_standup`
6. `weekly_report`
7. `risk_analysis`

### 3.11 Decision

用于记录规则、策略或 AI 生成的建议和动作。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 决策 ID |
| project_id | string | 是 | 关联项目 |
| source | enum | 是 | 来源 |
| autonomy_level | enum | 是 | 自治级别 |
| title | string | 是 | 决策标题 |
| content | text | 是 | 决策内容 |
| proposed_action | json | 否 | 建议动作 |
| status | enum | 是 | 决策状态 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

`source` 值：

1. `rule`
2. `strategy`
3. `ai`

`autonomy_level` 值：

1. `auto`
2. `approval`
3. `forbidden`

## 4. 事件模型

### 4.1 通用事件字段

所有内部事件都应包含：

```json
{
  "event_id": "evt_xxx",
  "event_type": "project.created",
  "idempotency_key": "project.created:project_xxx",
  "occurred_at": "2026-04-28T10:00:00+08:00",
  "source": "teamflow",
  "project_id": "project_xxx",
  "actor_open_id": "ou_xxx",
  "payload": {}
}
```

### 4.2 project.created

触发时机：项目记录成功创建后。

```json
{
  "event_type": "project.created",
  "idempotency_key": "project.created:{project_id}",
  "project_id": "project_xxx",
  "actor_open_id": "ou_xxx",
  "payload": {
    "project_name": "TeamFlow",
    "git_repo_path": "https://example.com/repo.git",
    "admin_open_id": "ou_xxx"
  }
}
```

### 4.3 project.workspace_initialized

触发时机：协作空间初始化完成或部分完成后。

```json
{
  "event_type": "project.workspace_initialized",
  "idempotency_key": "project.workspace_initialized:{project_id}:{attempt}",
  "project_id": "project_xxx",
  "actor_open_id": "system",
  "payload": {
    "workspace_status": "succeeded",
    "feishu_group_id": "oc_xxx",
    "feishu_group_link": "https://...",
    "feishu_doc_url": "https://...",
    "steps": [
      {"name": "create_group", "status": "succeeded"},
      {"name": "invite_admin", "status": "succeeded"},
      {"name": "create_doc", "status": "succeeded"}
    ]
  }
}
```

### 4.4 task.overdue

触发时机：任务超过截止时间且未完成。

```json
{
  "event_type": "task.overdue",
  "idempotency_key": "task.overdue:{project_id}:{task_id}:{due_date}",
  "project_id": "project_xxx",
  "actor_open_id": "system",
  "payload": {
    "task_id": "task_xxx",
    "task_title": "完成接口联调",
    "assignee_open_id": "ou_xxx",
    "due_at": "2026-04-27T18:00:00+08:00",
    "overdue_days": 1
  }
}
```

### 4.5 schedule.daily_standup

触发时机：每日站会摘要调度任务执行。

```json
{
  "event_type": "schedule.daily_standup",
  "idempotency_key": "schedule.daily_standup:{project_id}:{date}",
  "project_id": "project_xxx",
  "actor_open_id": "system",
  "payload": {
    "date": "2026-04-28",
    "timezone": "Asia/Shanghai"
  }
}
```

### 4.6 schedule.weekly_report

触发时机：每周周报调度任务执行。

```json
{
  "event_type": "schedule.weekly_report",
  "idempotency_key": "schedule.weekly_report:{project_id}:{week}",
  "project_id": "project_xxx",
  "actor_open_id": "system",
  "payload": {
    "week": "2026-W18",
    "timezone": "Asia/Shanghai"
  }
}
```

## 5. 幂等规则

1. 飞书原始事件用飞书 event_id 去重。
2. 内部业务事件用 `idempotency_key` 去重。
3. 创建飞书群前先检查项目记录是否已有 `feishu_group_id`。
4. 创建项目文档前先检查项目记录是否已有 `feishu_doc_url`。
5. 提醒类消息使用 `dedupe_key` 控制重复发送。
6. 定时报告以项目 ID 和日期或周编号作为幂等维度。
7. 卡片表单提交用 `request_id` 去重，重复提交返回当前状态卡片。
8. 协作空间初始化用 `workspace_status` 检查，`succeeded` 或 `partial_failed` 时跳过重复执行。

## 6. 脱敏规则

1. 日志中不得出现 App Secret、访问令牌、模型 API Key。
2. Git 仓库如果包含凭证，必须脱敏后存储或输出。
3. AI 输入日志只记录摘要，不默认保存完整用户私聊内容。
4. 错误信息要可定位问题，但不得泄露密钥。

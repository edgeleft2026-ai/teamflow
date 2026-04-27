# TeamFlow AI — 真实环境测试指导

> 本文档指导你在真实环境中一步步配置并验证 TeamFlow AI 的所有功能。
> 不是脚本测试，是手动配置 + 实际操作验证。

---

## 前置条件

| 项目 | 要求 |
|---|---|
| Python | 3.11+ |
| Git | 已安装，命令行可用 |
| 飞书账号 | 有管理员权限的飞书企业账号（用于创建应用） |
| LLM API Key | 至少一个（MiniMax / OpenAI / DeepSeek / GLM 等） |
| 操作系统 | macOS / Linux（本文以 macOS 为例） |

---

## 第一步：运行配置向导（含依赖检查）

TeamFlow 提供了交互式配置向导，**依赖检查是向导的第一个环节**，无需手动安装：

```bash
cd /Users/jarvis/Documents/Projects/teamflow
python -m app.cli.main setup
```

向导启动后会自动：

1. **检查依赖** — 扫描 13 个必装依赖（fastapi、uvicorn、openai、lark-oapi 等）和 1 个可选依赖（python-dotenv），缺失时提示安装（优先使用清华源）
2. **引导配置** — 模型提供商 → 飞书 → Agent 行为 → 项目

> **提示**：如果你更习惯手动安装依赖，也可以先执行：
> ```bash
> pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
> # 或
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```
> 然后再运行向导，此时向导会检测到依赖已就绪，直接进入配置环节。

向导会依次引导你完成：模型提供商 → 飞书 → Agent 行为 → 项目。下面逐项说明。

### 1.1 配置 LLM 模型提供商

向导中选 **Step 1: Model Provider**，或单独运行：

```bash
python -m app.cli.main model
```

**操作步骤：**

1. 从列表中选择你的提供商（如 MiniMax / OpenAI / DeepSeek / GLM 等）
2. 输入 API Key（输入时不会回显）
3. 选择是否自动探测可用模型（推荐选"是"）
4. 为 fast / smart / reasoning 三个层级各选一个模型
   - **fast**：日常简单任务（如消息摘要），选最便宜最快的
   - **smart**：复杂分析（如风险分析、周报生成），选最强模型
   - **reasoning**：深度推理（如策略改进），选推理能力最强的

**手动配置方式（如果向导不方便）：**

```bash
# 设置 API Key（以 MiniMax 为例）
python -m app.cli.main config set MINIMAX_API_KEY "你的key"

# 或者直接写入 ~/.teamflow/.env 文件
echo 'MINIMAX_API_KEY=你的key' >> ~/.teamflow/.env
```

**验证：**

```bash
python -m app.cli.main doctor
```

看到 `✓ 活跃提供商: MiniMax` 和 `✓ API Key: xxxx...xxxx` 即为成功。

### 1.2 配置飞书应用

向导中选 **Step 2: Feishu**，或单独运行：

```bash
python -m app.cli.main setup feishu
```

**方式一：扫码自动创建（推荐）**

1. 选择"扫码自动创建 Bot"
2. 终端会显示一个二维码（需要 `pip install qrcode`）
3. 用飞书手机端扫码
4. 扫码成功后自动获取 App ID 和 App Secret

**方式二：手动创建飞书应用**

1. 打开 [飞书开放平台](https://open.feishu.cn/app)，点击「创建应用」
2. 选择「企业自建应用」
3. 填写应用名称（如 "TeamFlow AI"），描述随意
4. 创建后进入应用详情页，复制 **App ID** 和 **App Secret**
5. 在向导中粘贴

**关键：启用机器人能力**

1. 在飞书开放平台 → 你的应用 → 左侧「添加应用能力」
2. 启用「机器人」
3. 在「权限管理」中开通以下权限：
   - `im:message` — 发送消息
   - `im:message:send_as_bot` — 以机器人身份发消息
   - `im:resource` — 获取消息中的资源
   - `im:chat` — 获取群信息
   - `approval:approval` — 审批
   - `task:task` — 任务
   - `calendar:calendar` — 日历
   - `wiki:wiki` — 知识库
   - `docx:document` — 文档
   - `mail:mail` — 邮件
   - `contact:user.id:readonly` — 读取用户 ID
4. 点击「批量开通」，然后「发布应用」

**配置连接模式：**

- **WebSocket（推荐）**：不需要公网 IP，飞书主动推送消息给你
- **Webhook**：需要你有公网可达的 HTTP 端点（可用 ngrok 代理）

**配置 DM 安全策略：**

- `配对审批（推荐）`：新用户私聊机器人需先审批
- `允许所有人私聊`
- `仅允许指定用户`

**验证：**

```bash
python -m app.cli.main doctor
# 看到 ✓ 飞书 App ID 和 ✓ Bot: xxx 即为成功
```

### 1.3 配置 Agent 行为和调度

向导中选 **Step 3: Agent**，或单独运行：

```bash
python -m app.cli.main setup agent
```

1. 选择哪些操作自动执行（建议全选：notify / status_infer / daily_summary / reminder）
2. 选择哪些操作需要审批（建议全选：reassign / priority_change / deadline_change / create_doc / update_doc）
3. 确认时区（默认 Asia/Shanghai）

### 1.4 配置项目

向导中选 **Step 4: Project**，或单独运行：

```bash
python -m app.cli.main setup project
```

1. 输入项目名称（如 "MyProject"）
2. 输入 Git 仓库路径（必须是本地已有仓库，如 `/Users/jarvis/Documents/Projects/myapp`）
3. 输入飞书群 ID（可选，后面也可以配）
4. 输入飞书知识库空间 ID（可选）

**如何获取飞书群 ID：**

1. 在飞书群聊设置中，找到「群二维码」
2. 二维码链接中 `chat_id=xxx` 的 xxx 就是群 ID
3. 或者通过 API 调用获取

---

## 第二步：启动服务

```bash
python -m app.cli.main run
```

服务启动后：
- HTTP API 监听在 `http://0.0.0.0:8000`
- 飞书 WebSocket 自动连接
- 定时任务自动开始调度
- 终端会显示一个简易 Dashboard

**验证服务启动：**

```bash
# 另开终端
curl http://localhost:8000/health
```

正常返回：

```json
{
  "status": "ok",
  "components": {
    "database": "ok",
    "scheduler": "ok",
    "agent": "ok",
    "feishu_ws": "connected"
  }
}
```

---

## 第三步：验证核心功能

### 3.1 项目管理 API

**创建项目：**

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试项目",
    "git_repo_path": "/Users/jarvis/Documents/Projects/teamflow"
  }'
```

返回 `{"id": 1, "name": "测试项目"}`。

**查询项目列表：**

```bash
curl http://localhost:8000/api/projects
```

### 3.2 成员管理

**添加成员：**

```bash
curl -X POST http://localhost:8000/api/projects/1/members \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "git_author_name": "zhangsan",
    "role": "member"
  }'
```

**再添加一个成员：**

```bash
curl -X POST http://localhost:8000/api/projects/1/members \
  -H "Content-Type: application/json" \
  -d '{
    "name": "李四",
    "git_author_name": "lisi",
    "role": "member"
  }'
```

### 3.3 任务管理

**创建任务：**

```bash
curl -X POST http://localhost:8000/api/projects/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "实现用户登录功能",
    "description": "需要支持手机号+验证码登录",
    "priority": "high",
    "assignee_id": 1,
    "deadline": "2026-04-20T18:00:00"
  }'
```

> 注意：deadline 设为过去的日期，用于后续测试逾期检测。

**创建更多测试任务：**

```bash
# 一个已过期的中优先级任务
curl -X POST http://localhost:8000/api/projects/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "编写 API 文档",
    "priority": "medium",
    "assignee_id": 1,
    "deadline": "2026-04-10T18:00:00"
  }'

# 一个未过期的低优先级任务
curl -X POST http://localhost:8000/api/projects/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "优化数据库查询性能",
    "priority": "low",
    "assignee_id": 2,
    "deadline": "2026-05-30T18:00:00"
  }'

# 一个无截止日期的任务（用于测试停滞检测）
curl -X POST http://localhost:8000/api/projects/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "重构日志模块",
    "priority": "medium",
    "assignee_id": 2
  }'
```

**查看任务列表：**

```bash
curl http://localhost:8000/api/projects/1/tasks
```

### 3.4 健康度评分

```bash
curl http://localhost:8000/api/projects/1/health
```

返回项目健康度评分（A/B/C/D/F），包含 5 个维度的分数。

**查看趋势：**

```bash
curl http://localhost:8000/api/projects/1/health/trend
```

### 3.5 观察记录和决策记录

```bash
# 查看观察记录
curl http://localhost:8000/api/projects/1/observations

# 查看决策记录
curl http://localhost:8000/api/projects/1/decisions
```

---

## 第四步：验证感知层

### 4.1 Git Monitor — 手动触发扫描

Git Monitor 默认每 30 分钟自动扫描。要手动触发，可以用 API 发起巡检：

```bash
curl -X POST http://localhost:8000/api/patrol
```

这会让 AI Agent 对所有项目执行一次巡检，包括 Git 扫描和任务扫描。

**验证 Git 数据采集：**

1. 在配置的 Git 仓库中做一次 commit：

```bash
cd /Users/jarvis/Documents/Projects/teamflow
echo "test" >> test_file.txt
git add test_file.txt
git commit -m "feat: test commit for TeamFlow"
```

2. 触发巡检：

```bash
curl -X POST http://localhost:8000/api/patrol
```

3. 查看观察记录，应该能看到 `git.new_commit` 类型的观察：

```bash
curl http://localhost:8000/api/projects/1/observations
```

### 4.2 Task Monitor — 逾期检测

Task Monitor 每日 10:00 自动扫描。我们之前创建了 deadline 在过去的任务，触发巡检后应该能检测到逾期：

```bash
curl -X POST http://localhost:8000/api/patrol
```

检查观察记录中是否有 `task.overdue` 事件。如果飞书已连接，飞书群中应该收到逾期提醒消息。

### 4.3 Event Bus — 事件发布验证

通过 API 直接发布一个事件来验证事件总线：

```bash
# 通过 chat 接口间接触发事件处理
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "/status"
  }'
```

---

## 第六步：验证飞书集成

### 6.1 WebSocket 连接

启动服务后，检查飞书 WebSocket 是否连接：

```bash
curl http://localhost:8000/health | python -m json.tool
```

`feishu_ws: connected` 表示已连接。

### 6.2 群聊 @机器人

1. 在飞书中创建一个群聊，把 TeamFlow 机器人拉入群
2. 在群中 @机器人 发消息，如：`@TeamFlow AI /status`
3. 机器人应该回复项目状态概览

**测试各种命令：**

| 命令 | 说明 |
|---|---|
| `@机器人 /status` | 项目状态概览 |
| `@机器人 /tasks` | 任务列表 |
| `@机器人 /tasks todo` | 待办任务 |
| `@机器人 /risk` | 风险分析 |
| `@机器人 /standup` | 站会摘要 |
| `@机器人 /help` | 帮助 |

### 6.3 私聊机器人

1. 在飞书中找到 TeamFlow 机器人
2. 发起私聊，发送 `/help`
3. 如果 DM 策略是 `allowlist`，首次私聊需要审批

**审批 DM 请求：**

```bash
# 查看待审批的 DM 请求
curl http://localhost:8000/api/sensitive-ops/pending
```

### 6.4 通知推送验证

创建一个逾期任务（deadline 设为过去），然后触发巡检，飞书群应收到逾期提醒。

### 6.5 审批流验证

当 AI 建议执行 `approval` 级别的操作时（如重新分配任务），会发送飞书审批卡片。

手动触发一个需要审批的操作：

```bash
# 通过 chat 让 AI 建议重新分配任务
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "张三任务太多了，建议重新分配"
  }'
```

飞书群中应收到审批卡片，点击「同意」或「拒绝」。

### 6.6 消息聚合验证

短时间内触发多条通知（如连续创建多个逾期任务），消息应被聚合为一条发送，而不是逐条轰炸。

---

## 第七步：验证决策引擎

### 7.1 规则引擎匹配

规则定义在 `config/rules.yaml`，当前有 7 条规则。验证规则匹配：

**测试逾期提醒规则：**

1. 创建一个 deadline 在过去的任务
2. 触发巡检
3. 规则引擎应匹配 `task.overdue` → `overdue_task_reminder` 规则
4. 自动发送逾期提醒（autonomy: auto）

**测试停滞提醒规则：**

1. 创建一个任务，3 天不更新
2. 触发巡检
3. 规则引擎应匹配 `task.stale` → `stale_task_reminder` 规则

> 注意：停滞检测基于 `updated_at` 字段，新创建的任务不会立即被判定为停滞。可以手动修改数据库中的 `updated_at` 来模拟：

```bash
sqlite3 data/teamflow.db "UPDATE tasks SET updated_at='2026-04-20T10:00:00' WHERE id=4"
```

### 7.2 策略引擎匹配

策略定义在 `strategies/active/` 目录，当前有 3 个策略。验证策略匹配：

**测试逾期任务提醒策略：**

策略文件 `overdue-task-reminder.md` 的触发器是 `task.overdue`，条件是 `days_overdue > 0`。

1. 创建逾期任务
2. 触发巡检
3. 策略引擎应匹配此策略
4. 查看决策记录确认

```bash
curl http://localhost:8000/api/projects/1/decisions
```

### 7.3 LLM Fallback

当规则和策略都没匹配时，决策引擎会调用 LLM 分析事件。

**测试方法：**

1. 发布一个不常见的事件类型（没有对应规则和策略）
2. 观察 LLM 是否被调用并给出建议

可以通过修改事件类型来模拟：

```bash
# 直接通过 API 发送一条自然语言消息，触发 LLM 处理
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "项目最近进展怎么样？有什么风险吗？"
  }'
```

LLM 会基于项目上下文回答。

---

## 第八步：验证定时任务

### 8.1 查看定时任务状态

```bash
# 通过 API 查看调度器状态（如果有的话）
# 或者查看日志
tail -f data/logs/server.log | grep "Scheduler"
```

### 8.2 手动触发定时任务

定时任务在 `app/scheduler/jobs.py` 中定义。要手动触发，可以通过巡检 API：

```bash
# 触发完整巡检（包含 git_activity_scan + overdue_scan + stale_task_scan 等）
curl -X POST http://localhost:8000/api/patrol
```

### 8.3 验证站会摘要

站会摘要默认工作日 9:00 自动生成。手动触发：

```bash
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "command": "/standup"
  }'
```

应返回包含以下内容的站会摘要：
- 昨日完成的任务
- 今日待办
- 阻塞项
- 风险提示

### 8.4 验证周报

```bash
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "command": "/report"
  }'
```

周报会尝试创建飞书文档并推送链接到群。

### 8.5 验证健康度评分

每日 8:00 自动计算。手动触发：

```bash
curl http://localhost:8000/api/projects/1/health
```

---

## 第九步：验证自主权控制

### 9.1 自动执行（auto）

`notify`、`status_infer`、`daily_summary`、`reminder` 这些操作会自动执行，无需审批。

**验证：**

1. 创建逾期任务
2. 触发巡检
3. 逾期提醒应自动发送，无需人工确认

### 9.2 需审批（approval）

`reassign`、`priority_change`、`deadline_change`、`create_doc`、`update_doc` 需要审批。

**验证审批流程：**

1. 让 AI 建议重新分配任务（如某成员过载）
2. 飞书群中应收到审批卡片
3. 点击「同意」→ 操作执行
4. 点击「拒绝」→ 操作取消

**通过 API 查看审批状态：**

```bash
# 查看待审批
curl http://localhost:8000/api/sensitive-ops/pending

# 手动同意
curl -X POST http://localhost:8000/api/sensitive-ops/confirm \
  -H "Content-Type: application/json" \
  -d '{"request_id": "审批ID"}'

# 手动拒绝
curl -X POST http://localhost:8000/api/sensitive-ops/reject \
  -H "Content-Type: application/json" \
  -d '{"request_id": "审批ID", "reason": "不需要重新分配"}'
```

### 9.3 禁止自动（forbidden）

`delete_task`、`remove_member`、`close_project` 禁止自动执行，即使审批也不行。

**验证：**

尝试让 AI 删除任务，应该被拒绝。

### 9.4 审批超时

审批请求有 24 小时超时机制：
- 24 小时未处理 → 发送提醒
- 再过 24 小时仍未处理 → 自动取消

**模拟超时：** 实际等待 24 小时太长，可以查看数据库中的 `approval_requests` 表确认超时逻辑已注册。

---

## 第十步：验证策略系统

### 10.1 查看现有策略

```bash
curl http://localhost:8000/api/strategies
```

应返回 3 个活跃策略：

- `overdue-task-reminder` — 逾期提醒
- `stale-branch-alert` — 过期分支提醒
- `member-overload-rebalance` — 成员过载重分配

### 10.2 创建新策略

```bash
curl -X POST http://localhost:8000/api/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pr-merge-notification",
    "trigger": "git.pr_merged",
    "condition": "",
    "action": "notify",
    "autonomy": "auto",
    "body": "# PR 合并通知\n\n合并分支：{branch}\n合并信息：{merge_message}"
  }'
```

验证策略文件已创建：

```bash
ls strategies/active/pr-merge-notification.md
```

### 10.3 策略效果追踪

每次策略触发后，效果分数会更新。查看策略效果：

```bash
curl http://localhost:8000/api/strategies
```

`effectiveness` 字段反映策略效果（0.0 ~ 1.0）。

### 10.4 策略自进化

- 效果分数持续低于 0.5 → 自动降级为 approval 模式
- 30 天未触发 → 自动归档到 `strategies/inactive/`

**手动归档过期策略：**

```bash
curl -X POST http://localhost:8000/api/strategies/archive-stale
```

### 10.5 A/B 测试

**创建 A/B 测试：**

```bash
curl -X POST http://localhost:8000/api/ab-tests \
  -H "Content-Type: application/json" \
  -d '{
    "trigger": "task.overdue",
    "strategy_names": ["overdue-task-reminder", "pr-merge-notification"]
  }'
```

**查看活跃测试：**

```bash
curl http://localhost:8000/api/ab-tests
```

**结束测试：**

```bash
curl -X POST http://localhost:8000/api/ab-tests/{test_id}/conclude
```

---

## 第十一步：验证人机对话

### 11.1 结构化命令

```bash
# 项目状态
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "command": "/status"}'

# 任务列表
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "command": "/tasks"}'

# 风险分析
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "command": "/risk"}'

# 帮助
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "command": "/help"}'
```

### 11.2 自然语言对话

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "项目有什么风险？"
  }'
```

LLM 会基于项目上下文（任务、成员、Git 活动）给出回答。

### 11.3 飞书群对话

在飞书群中 @机器人 直接提问：

- `@TeamFlow AI 项目进展怎么样？`
- `@TeamFlow AI 张三在做什么？`
- `@TeamFlow AI 有什么阻塞的任务吗？`

---

## 第十二步：验证高级功能

### 12.1 子代理并行巡检

```bash
# 查看子代理状态
curl http://localhost:8000/api/sub-agents/status

# 触发并行巡检（多项目时才有意义）
curl -X POST http://localhost:8000/api/sub-agents/patrol
```

需要配置 2 个以上项目才能看到并行效果。

### 12.2 记忆管理

```bash
# 查看项目记忆
curl http://localhost:8000/api/projects/1/memory

# 预取记忆（在 LLM 调用前加载上下文）
curl -X POST http://localhost:8000/api/projects/1/memory/prefetch

# 同步记忆
curl -X POST http://localhost:8000/api/projects/1/memory/sync
```

### 12.3 人格系统

```bash
# 查看当前人格
curl http://localhost:8000/api/projects/1/personality
```

人格定义在 `PM_STYLE.md` 文件中，可以自定义 AI 项目经理的风格。

### 12.4 凭据池

```bash
# 查看凭据池状态
curl http://localhost:8000/api/credentials
```

如果配置了多个 API Key，可以看到轮转状态和冷却情况。

### 12.5 Prometheus 指标

```bash
curl http://localhost:8000/api/metrics
```

返回 Prometheus 格式的指标数据，包含：
- 系统指标（CPU、内存、请求数）
- 业务指标（任务数、决策数、LLM 调用数）

### 12.6 Webhook 安全

如果使用 Webhook 模式（非 WebSocket），验证签名校验：

```bash
# 发送一个带错误签名的请求，应被拒绝
curl -X POST http://localhost:8000/api/webhooks/feishu \
  -H "Content-Type: application/json" \
  -H "X-Lark-Signature-Timestamp: 1234567890" \
  -H "X-Lark-Signature: invalid_signature" \
  -d '{"type": "url_verification", "challenge": "test", "token": "wrong"}'
```

应返回 403。

---

## 第十三步：验证飞书 Action 深度功能

### 13.1 飞书文档创建

当 AI 决定创建文档时（如周报），会调用 FeishuDocAction：

```bash
# 通过 chat 触发文档创建
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "帮我生成本周的项目周报文档"
  }'
```

> 需要 `lark-cli` 已安装并登录。安装方式：`npm install -g lark-cli`，然后 `lark-cli auth login`。

### 13.2 飞书邮件

```bash
# 通过 chat 触发邮件发送
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "message": "给张三发一封邮件，提醒他处理逾期任务"
  }'
```

> 需要飞书应用有邮件权限，且成员配置了 email 字段。

### 13.3 飞书日历

```bash
# 建议会议时间
curl -X POST http://localhost:8000/api/projects/1/calendar/suggest \
  -H "Content-Type: application/json" \
  -d '{"duration_minutes": 60, "participants": ["张三", "李四"]}'
```

---

## 第十四步：端到端场景验证

### 场景 1：逾期任务自动提醒

1. 创建一个 deadline 在过去的任务，分配给张三
2. 触发巡检：`curl -X POST http://localhost:8000/api/patrol`
3. 预期结果：
   - Task Monitor 检测到逾期
   - Event Bus 发布 `task.overdue` 事件
   - Decision Engine 匹配规则 `overdue_task_reminder`
   - FeishuNotifyAction 自动发送逾期提醒到飞书群
   - 飞书群收到消息

### 场景 2：成员过载 → 审批重分配

1. 给张三分配 5 个以上任务
2. 触发巡检
3. 预期结果：
   - Task Monitor 检测到 `member.overloaded`
   - Decision Engine 匹配策略 `member-overload-rebalance`
   - 因为 autonomy 是 `approval`，发送飞书审批卡片
   - 管理员点击「同意」→ SuggestReassignmentAction 执行
   - 任务被重新分配给空闲成员

### 场景 3：Git 提交 → 任务状态自动推进

1. 创建一个 todo 状态的任务，关联 git_branch
2. 在该分支上做 commit
3. 触发 Git 扫描
4. 预期结果：
   - Git Monitor 检测到新 commit
   - 推断任务进度，将 todo → in_progress
   - 发布 `git.new_commit` 事件

### 场景 4：自然语言查询

1. 在飞书群 @机器人 问："项目有什么风险？"
2. 预期结果：
   - ConversationHandler 接收消息
   - LLM 基于项目上下文分析
   - 返回风险分析结果

### 场景 5：策略自进化

1. 创建一个测试策略，effectiveness 设为 0.3
2. 触发多次（至少 5 次），让效果分数持续低
3. 预期结果：
   - StrategyEvolver 自动将 autonomy 从 auto 降级为 approval
   - 策略文件被更新

---

## 第十五步：诊断和排错

### 15.1 Doctor 诊断

```bash
python -m app.cli.main doctor
```

自动检查：配置文件、LLM 提供商、飞书连接、数据库、依赖、网络连通性。

### 15.2 查看日志

```bash
# 实时日志
tail -f data/logs/server.log

# 过滤特定模块
tail -f data/logs/server.log | grep "DecisionEngine"
tail -f data/logs/server.log | grep "GitMonitor"
tail -f data/logs/server.log | grep "TaskMonitor"
tail -f data/logs/server.log | grep "FeishuWS"
```

### 15.3 查看数据库

```bash
sqlite3 data/teamflow.db

# 常用查询
.tables
SELECT * FROM projects;
SELECT * FROM tasks;
SELECT * FROM observations ORDER BY created_at DESC LIMIT 10;
SELECT * FROM decisions ORDER BY created_at DESC LIMIT 10;
SELECT * FROM approval_requests;
SELECT * FROM conversations ORDER BY created_at DESC LIMIT 10;
```

### 15.4 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 飞书 WebSocket 连不上 | App ID/Secret 错误或应用未发布 | 检查凭据，确保应用已发布 |
| LLM 调用失败 | API Key 无效或余额不足 | 运行 `teamflow doctor` 检查连通性 |
| Git 扫描无数据 | 仓库路径错误或无 commit | 确认路径正确，仓库有 commit 历史 |
| 定时任务不执行 | 时区配置错误 | 检查 `scheduler.timezone` 配置 |
| 审批卡片不出现 | 飞书应用缺少审批权限 | 在开放平台添加审批能力 |
| 消息重复发送 | 消息去重未生效 | 检查 `data/message_dedup.json` 是否正常 |

---

## 配置文件位置速查

| 文件 | 路径 | 说明 |
|---|---|---|
| 主配置 | `~/.teamflow/config.yaml` | 项目、调度、自主权等 |
| 环境变量 | `~/.teamflow/.env` | API Key 等敏感信息 |
| 规则 | `config/rules.yaml` | 决策规则定义 |
| 活跃策略 | `strategies/active/*.md` | 策略文件 |
| 归档策略 | `strategies/inactive/*.md` | 已淘汰策略 |
| 人格 | `PM_STYLE.md` | AI 项目经理风格 |
| 事件钩子 | `hooks/*/HOOK.yaml` | 自定义钩子 |
| 数据库 | `data/teamflow.db` | SQLite 数据 |
| 日志 | `data/logs/server.log` | 运行日志 |
| LLM 追踪 | `data/llm_tracking.json` | LLM 调用记录 |
| 审计日志 | `data/audit/` | 决策审计 |
| 消息去重 | `data/message_dedup.json` | 飞书消息去重 |

---

## 测试检查清单

完成以上所有步骤后，用此清单确认：

- [ ] 依赖安装成功，`teamflow doctor` 无错误
- [ ] LLM 提供商配置成功，API 可连通
- [ ] 飞书应用创建成功，WebSocket 已连接
- [ ] 项目创建成功，Git 仓库路径正确
- [ ] 成员添加成功
- [ ] 任务创建成功
- [ ] 巡检触发成功，Git 数据采集正常
- [ ] 逾期任务检测正常，飞书群收到提醒
- [ ] 规则引擎匹配正常
- [ ] 策略引擎匹配正常
- [ ] LLM Fallback 正常（自然语言对话有回复）
- [ ] 审批流程正常（卡片发送、同意/拒绝）
- [ ] 站会摘要生成正常
- [ ] 周报生成正常
- [ ] 健康度评分正常
- [ ] 策略创建/归档正常
- [ ] A/B 测试创建/结束正常
- [ ] 飞书群 @机器人 对话正常
- [ ] 私聊机器人正常
- [ ] Prometheus 指标可访问
- [ ] 子代理并行巡检正常
- [ ] 记忆管理正常
- [ ] 端到端场景全部通过

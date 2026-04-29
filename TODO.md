# TeamFlow 开发路线 TODO

本 TODO 与 `docs/prd/` 下的 PRD 保持一致。开发时优先按 M0 到 M4 顺序推进，避免在主链路稳定前提前扩展复杂能力。

## M0：飞书交互链路打通

目标：验证飞书消息能收能发，是所有后续功能的地基。

### 项目基础设施

- [x] Python 项目骨架：pyproject.toml + src/teamflow/ 目录结构
- [x] 配置模块：`config/settings.py` + `config.example.yaml`
- [x] 执行层封装：`execution/cli.py` — lark-cli subprocess 调用 + tenant_access_token 自动交换与注入
- [x] `pip install -e .` 验证通过
- [x] CLI 入口：`teamflow setup` / `teamflow run` 命令行工具（`__main__.py`）

### CLI 基础设施

- [x] 安装 lark-cli 二进制（从 cli/ 源码编译）
- [x] 验证 CLI 基础命令可用：`lark-cli --help`
- [x] Setup 命令：QR 扫码自动创建飞书应用 + 手动凭证输入（`setup/feishu.py` + `setup/cli.py`）
- [x] 创建 config.yaml（运行 `teamflow setup` 或手动填写真实凭证）
- [x] 验证凭证注入：执行层自动交换 tenant_access_token，bot 身份 API 调用正常

### 事件接入

- [x] 启动 `lark-cli event +subscribe` 长驻进程（`main.py` 中实现）
- [x] 配置事件类型：`im.message.receive_v1` 等
- [x] 实现文件监听：`access/watcher.py` — EventFileWatcher 监听 NDJSON 事件文件
- [x] 飞书原始事件去重：`access/dispatcher.py` — EventDispatcher 按 event_id 去重
- [x] Bot 自身消息过滤：`access/parser.py` — is_bot_message() 检查 sender_type

### 消息处理

- [x] 私聊消息接收与解析：`access/parser.py` — parse_ndjson_line + extract_*
- [x] 群消息接收与解析：同一套解析逻辑
- [x] 从消息上下文提取用户 open_id：extract_open_id()

### 消息发送

- [x] 封装 `send_message()` → `execution/messages.py`
- [x] 主动发送私聊消息：send_message(user_id=...)
- [x] 主动发送群消息：send_message(chat_id=...)

### 运维

- [x] 接入日志：logging 框架记录消息进入、解析结果、忽略原因
- [x] `/health` 轻量健康检查：main.py 中 HTTPServer 响应
- [x] 端到端验证：用户发消息 -> 服务收到事件 -> 服务回复消息（已通过真实凭证验证）

验收依据：`docs/prd/03-acceptance-checklist.md` 的 M0 部分。

---

## M1：项目创建可用

目标：用户能在飞书中发起项目创建，完成信息收集、项目落库、管理员绑定和创建结果回执。

- [x] 欢迎引导消息：首次触达或 `/help` 时展示可用能力
- [x] "开始创建项目"触发识别
- [x] 分步信息收集状态机
  - [x] `idle` -> `collecting_project_name`
  - [x] `collecting_project_name` -> `collecting_repo`
  - [x] `collecting_repo` -> `creating_project`
  - [x] `creating_project` -> `created` / `failed`
- [x] 会话状态持久化：保存 open_id、chat_id、flow、state、payload、expires_at
- [x] 项目名称收集与校验：非空
- [x] Git 仓库地址或本地路径收集与校验：非空
- [x] 项目记录写入数据库：id、name、git_repo_path、admin_open_id、status、created_at、updated_at
- [x] 管理员绑定：从消息上下文获取 open_id
- [x] 创建成功回执：项目 ID、项目名、后续初始化提示
- [x] 创建失败回执：失败步骤、原因、可执行下一步
- [x] 发布 `project.created` 事件
- [x] 事件写入 `EventLog`，包含 idempotency_key
- [x] 动作写入 `ActionLog`
- [x] 异常处理
  - [x] 用户中途退出 -> 提示当前阶段
  - [x] 重复触发创建 -> 允许重新开始或覆盖旧流程
  - [x] 输入为空 -> 提示重新输入
  - [x] 飞书身份解析失败 -> 明确报错并记录日志

验收依据：`docs/prd/modules/01-project-entry-and-onboarding.md`。

---

## Agent 基础设施

目标：搭建 Agent 执行通道，为 M2+ 的复杂编排提供能力。M0+M1 的确定性通道代码完全保留不动。

### MCP Server 集成

- [ ] 安装 Node.js LTS 运行时
- [ ] 验证 `npx @larksuiteoapi/lark-mcp mcp -a <app_id> -s <app_secret>` 可启动
- [ ] 配置 MCP Server 工具集：M2 阶段启用 `im.v1.*`, `docx.v1.*`
- [ ] MCP Server 子进程生命周期管理：启动、健康检查、异常重启

### MCP Client 集成

- [ ] 安装 Python MCP SDK：`pip install mcp`
- [ ] 实现 `ai/mcp.py`：MCP 客户端连接管理（stdio transport）
- [ ] 实现 `tools/list` 工具发现，缓存可用工具列表
- [ ] 实现 `call_tool()` 封装：调用 MCP 工具并返回结构化结果
- [ ] MCP 连接异常处理与重连

### Agent Executor

- [ ] 实现 `ai/agent.py`：LiteLLM + tool-use 执行循环
- [ ] 实现 `AgentTask` / `AgentResult` 数据结构
- [ ] 实现 `ai/models.py`：模型路由（fast/smart/reasoning）与降级策略
- [ ] 实现 `ai/prompts.py`：Agent 系统提示词管理
- [ ] Agent 循环安全机制：max_iterations 限制、超时控制
- [ ] Agent 执行日志与审计：记录每次工具调用和结果

### 配置扩展

- [ ] `config/settings.py` 新增 Agent 配置：模型选择、MCP 工具集、max_iterations
- [ ] `config.example.yaml` 新增 Agent 配置段
- [ ] `main.py` 集成 MCP Server 启动和 Agent 初始化

### 端到端验证

- [ ] Agent 端到端测试：Python Agent → MCP Client → MCP Server → 飞书 API
- [ ] 验证工具发现：Agent 能列出飞书 API 工具
- [ ] 验证工具调用：Agent 能通过 MCP 创建群/文档
- [ ] 验证确定性通道不受影响：现有 M0+M1 功能正常

---

## M2：飞书工作空间可用

目标：项目创建后自动初始化飞书协作空间。多步编排走 Agent 智能通道，单步确认走确定性通道。

### 编排层改造

- [ ] 监听 `project.created` 事件
- [ ] 校验 `project.created` 幂等键
- [ ] 读取项目基础信息
- [ ] 构建 Agent 任务描述：项目名、管理员 open_id、初始化清单

### Agent 执行：工作空间初始化

- [ ] Agent 任务：创建群 + 拉人 + 创建文档 + 发欢迎语
- [ ] Agent 上下文注入：项目信息、管理员信息
- [ ] Agent 处理部分失败：某步失败不阻断后续，收集所有结果
- [ ] Agent 结果解析：提取群 ID、群链接、文档 URL

### 确定性通道：结果回写与通知

- [ ] 群 ID、群链接、文档 URL、初始化状态写回项目记录
- [ ] 向管理员发送初始化结果回执（确定性通道：send_card）
- [ ] 发布 `project.workspace_initialized` 事件

### 异常处理

- [ ] 幂等保障：同一项目不重复创建群和文档
- [ ] 单步失败不遮蔽其他已完成结果
- [ ] Agent 执行超时或失败 → 降级为分步确定性通道执行
- [ ] 回执发送失败 → 记录日志，可补偿

验收依据：`docs/prd/modules/02-feishu-workspace.md`。

---

## M3：项目运行与协作可用

目标：项目进入执行期后，系统能自动提醒风险、生成报告、响应查询。

### 3.1 数据准备

- [ ] 任务表：title、assignee_open_id、status、due_at、blocked_reason、last_activity_at、source
- [ ] 成员表：open_id、display_name、role、status
- [ ] Git 活动数据接入或导入
- [ ] 观察记录表：type、severity、title、content、evidence、dedupe_key
- [ ] 决策记录表：source、autonomy_level、proposed_action、status

### 3.2 提醒能力（确定性通道 + Agent 混合）

- [ ] 逾期提醒：任务过截止时间且未完成
- [ ] 阻塞提醒：任务被标记阻塞或存在阻塞原因
- [ ] 停滞提醒：任务或分支长时间无更新
- [ ] 成员负载提醒：成员负载显著高于团队平均
- [ ] 提醒消息去重与聚合
- [ ] 提醒写入 Observation

### 3.3 报告能力（Agent 智能通道）

- [ ] MCP 工具集扩展：启用 `calendar.v1.*`, `task.v1.*`, `sheet.v1.*`
- [ ] 每日站会摘要：Agent 聚合数据 + AI 生成内容
- [ ] 每周周报：Agent 分析 + AI 写作
- [ ] 风险分析报告：Agent 推理 + 建议生成
- [ ] Agent 输出写入 Observation / Decision

### 3.4 查询能力（Agent 智能通道）

- [ ] `/help`
- [ ] `/status`
- [ ] `/tasks`
- [ ] `/risk`
- [ ] `/standup`
- [ ] `/report`
- [ ] Agent 理解自然语言查询意图
- [ ] 数据为空时返回空状态说明

### 3.5 消息路由与调度

- [ ] 群通知：确定性通道发送
- [ ] 管理员私聊：确定性通道发送
- [ ] 高价值风险同时发群和私聊
- [ ] 每日站会摘要定时触发 → Agent 生成 + 确定性通道发送
- [ ] 每周周报定时触发 → Agent 生成 + 确定性通道发送
- [ ] 逾期任务定时扫描
- [ ] 停滞任务定时扫描
- [ ] Git 活动定时扫描

验收依据：`docs/prd/modules/03-project-operations-and-collaboration.md`。

---

## M4：AI 能力增强

目标：在规则和策略基础上叠加 AI 分析，实现更智能的风险判断、建议生成和受控自动决策。

### 4.1 分层决策机制

- [ ] 规则层：高确定性事件直接处理（确定性通道）
- [ ] 策略层：模板化场景策略匹配
- [ ] AI 分析层：Agent 处理复杂风险归因、周报总结、自然语言问答
- [ ] 决策结果写入 Decision

### 4.2 自治级别控制

- [ ] `auto`：通知、汇总、提醒、写入观察记录
- [ ] `approval`：重分配任务、更改优先级、更新重要文档
- [ ] `forbidden`：删除数据、移除成员、关闭项目、修改审计记录
- [ ] Agent 工具白名单与自治级别映射

### 4.3 提示词体系

- [ ] 系统角色提示词（Agent 系统提示）
- [ ] 风险分析提示词
- [ ] 每日站会提示词
- [ ] 每周周报提示词
- [ ] 任务建议提示词
- [ ] 自然语言问答提示词
- [ ] 输出格式校验和失败修复

### 4.4 模型层级

- [ ] `fast`：简单摘要、命令响应、低成本文本
- [ ] `smart`：风险分析、周报、站会摘要
- [ ] `reasoning`：复杂推理、策略生成、多约束判断

### 4.5 风险控制

- [ ] 无数据依据时不强推结论
- [ ] 输出建议带条件说明
- [ ] 高风险动作不自动执行
- [ ] AI 输出失败时退回规则或基础文案
- [ ] 日志中不记录完整敏感输入

验收依据：`docs/prd/modules/04-ai-analysis-and-decision.md`。

---

## 横切：平台支撑与可观测性

目标：保障核心链路稳定、可追踪、可定位问题。

### 接入与执行

- [x] 三层架构：接入层 -> 业务编排层 -> 执行层
- [x] Python 执行层封装：`execution/cli.py` 封装 lark-cli subprocess 调用 + 环境变量注入
- [ ] 双通道调度：编排层根据动作复杂度选择确定性/智能通道
- [ ] Agent 执行通道：`ai/agent.py` + `ai/mcp.py`
- [x] 执行结果结构化：`CLIResult` 返回 success、output、error、stderr_log
- [ ] Agent 结果结构化：`AgentResult` 返回 success、summary、actions
- [ ] CLI 日志解析：解析 CLI stderr 提取结构化信息写入 ActionLog
- [ ] Agent 审计日志：记录 Agent 工具调用链和结果
- [ ] 进程管理：三个子进程（事件订阅、MCP Server、健康检查）监控和自动重启

### 数据存储

- [x] ConversationState
- [x] EventLog
- [x] ActionLog
- [ ] Project（status 字段扩展：workspace 初始化相关状态）
- [ ] Member
- [ ] Task
- [ ] Observation
- [ ] Decision

### 日志与审计

- [x] 接入日志
- [ ] 编排日志（含通道选择决策）
- [x] 执行日志（确定性通道）
- [ ] Agent 执行日志（智能通道：工具调用链）
- [ ] 调度日志
- [ ] 模型调用摘要日志
- [ ] 审计记录：项目创建、空间初始化、高风险建议、用户审批、自动执行、配置变更
- [ ] 日志脱敏：密钥、令牌、API Key 不入日志

### 健康检查

- [x] 轻量健康检查：服务存活
- [ ] 详细健康检查：数据库、飞书连接、MCP Server 状态、调度器、模型配置
- [ ] 配置缺失时健康检查暴露明确错误

### 配置管理

- [x] 飞书配置独立管理
- [ ] 模型配置独立管理（LiteLLM model routing）
- [ ] Agent 配置独立管理（max_iterations、工具集、自治级别）
- [ ] 调度配置独立管理
- [ ] 环境变量 + 配置文件双支持

验收依据：`docs/prd/modules/05-platform-and-observability.md`。

---

## 发布前阻断项

- [x] 飞书消息收发链路可用
- [x] 项目创建成功后能落库
- [ ] Agent 能通过 MCP 调用飞书 API
- [ ] 重复事件不会创建重复群或重复文档
- [ ] 初始化失败有用户可见反馈
- [ ] 关键动作都有日志和审计记录（含 Agent 工具调用链）
- [ ] 日志中没有密钥或访问令牌
- [ ] 高风险动作不会绕过审批直接执行
- [ ] Agent 执行有 max_iterations 上限防止无限循环

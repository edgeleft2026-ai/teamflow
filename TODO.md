# TeamFlow 开发路线 TODO

本 TODO 与 `docs/prd/` 下的 PRD 保持一致。开发时优先按 M0 到 M4 顺序推进，避免在主链路稳定前提前扩展复杂能力。

## M0：飞书交互链路打通

目标：验证飞书消息能收能发，是所有后续功能的地基。

### 项目基础设施

- [x] Python 项目骨架：pyproject.toml + src/teamflow/ 目录结构
- [x] 配置模块：`config/settings.py` + `config.example.yaml`
- [x] 执行层封装：`execution/cli.py` — lark-cli subprocess 调用 + tenant_access_token 自动交换与注入
- [x] `pip install -e .` 验证通过
- [x] CLI 入口：`teamflow setup` / `teamflow run` / `teamflow reset` 命令行工具（`__main__.py`）

### CLI 基础设施

- [x] 安装 lark-cli 二进制（从 cli/ 源码编译）
- [x] 验证 CLI 基础命令可用：`lark-cli --help`
- [x] Setup 命令：QR 扫码自动创建飞书应用 + 手动凭证输入（`setup/feishu.py` + `setup/cli.py`）
- [x] 创建 config.yaml（运行 `teamflow setup` 或手动填写真实凭证）
- [x] 验证凭证注入：执行层自动交换 tenant_access_token，bot 身份 API 调用正常

### 事件接入

- [x] 启动 `lark-cli event +subscribe` 长驻进程（`main.py` 中实现）
- [x] 配置事件类型：`im.message.receive_v1` + `card.action.trigger`
- [x] 实现文件监听：`access/watcher.py` — EventFileWatcher 监听 NDJSON 事件文件
- [x] 飞书原始事件去重：`access/dispatcher.py` — EventDispatcher 按 event_id 去重
- [x] Bot 自身消息过滤：`access/parser.py` — is_bot_message() 检查 sender_type
- [x] 卡片动作事件解析：`access/parser.py` — extract_card_action_data() 解析 card.action.trigger
- [x] WebSocket 卡片回调：`access/callback.py` — lark-oapi WebSocket 长连接接收卡片交互事件

### 消息处理

- [x] 私聊消息接收与解析：`access/parser.py` — parse_ndjson_line + extract_*
- [x] 群消息接收与解析：同一套解析逻辑
- [x] 从消息上下文提取用户 open_id：extract_open_id()

### 消息发送

- [x] 封装 `send_message()` → `execution/messages.py`
- [x] 主动发送私聊消息：send_message(user_id=...)
- [x] 主动发送群消息：send_message(chat_id=...)
- [x] 发送交互卡片消息：send_card() — 支持 interactive 类型
- [x] 更新已发送卡片消息：update_card_message() — lark-oapi SDK patch
- [x] 异步消息发送：send_text_async / send_card_async / update_card_message_async

### 运维

- [x] 接入日志：logging 框架记录消息进入、解析结果、忽略原因
- [x] `/health` 轻量健康检查：main.py 中 HTTPServer 响应
- [x] 启动自检通知：启动时向管理员发送就绪卡片（admin_open_id 配置时）
- [x] 端到端验证：用户发消息 -> 服务收到事件 -> 服务回复消息（已通过真实凭证验证）

验收依据：`docs/prd/03-acceptance-checklist.md` 的 M0 部分。

---

## M1：项目创建可用

目标：用户能在飞书中发起项目创建，完成信息收集、项目落库、管理员绑定和创建结果回执。

### 文本式创建流程

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

### 卡片表单创建流程

- [x] 项目创建表单卡片：`orchestration/card_templates.py` — project_create_form_card()
- [x] 表单提交处理：ProjectCreateFlow.submit_form() — 接收卡片表单数据
- [x] 表单提交记录：`ProjectFormSubmission` 模型持久化 request_id、open_message_id、steps_payload
- [x] 进度卡片实时更新：创建过程中逐步更新同一张卡片显示当前步骤和状态
- [x] 后台 Worker 执行：表单提交后在独立线程中执行创建流程，不阻塞卡片回调响应
- [x] 卡片回调路由：CommandRouter.handle_card_action() — 路由 submit_project_form 等卡片动作

### 异常处理

- [x] 用户中途退出 -> 提示当前阶段
- [x] 重复触发创建 -> 允许重新开始或覆盖旧流程
- [x] 输入为空 -> 提示重新输入
- [x] 飞书身份解析失败 -> 明确报错并记录日志
- [x] 表单字段为空 -> 返回 toast 错误提示
- [x] 重复表单提交 -> 返回当前状态卡片

验收依据：`docs/prd/modules/01-project-entry-and-onboarding.md`。

---

## Agent 基础设施

目标：搭建 Agent 执行通道，为 M2+ 的复杂编排提供能力。M0+M1 的确定性通道代码完全保留不动。

> 设计演进：最初采用 MCP 协议（`@larksuiteoapi/lark-mcp` MCP Server + Python `mcp` SDK），因飞书 MCP Server v0.5.1 协议不兼容（`tools/list` 返回 Method not found），改为 **ToolProvider**（Python 原生，`lark-oapi` SDK 直连飞书 API，零外部进程依赖）。MCP 方案待飞书官方更新后可平滑切换回。

### 工具系统 (`ai/tools/`)

- [x] `ToolProvider` + `ToolDef`：注册 Python 异步函数为 Agent 工具，与 AgentExecutor 解耦
- [x] `ai/tools/feishu.py`：10+ 飞书 API 工具，使用 `lark-oapi` SDK
  - [x] IM Chat 工具：`im.v1.chat.create`、`im.v1.chat.members.create`、`im.v1.chat.get`、`im.v1.chat.link`
  - [x] IM Message 工具：`im.v1.message.create`（支持 text 和 interactive 类型）
  - [x] Docx 工具：`docx.v1.document.create`
  - [x] Drive 权限工具：`drive.v1.permission.add_collaborator`（文档协作者添加）
  - [x] Drive 权限工具：`drive.v1.permission.transfer_owner`（文档所有权转交）
  - [x] Bot 工具：`im.v1.bot.info`
  - [x] 通用 CLI 工具：`lark_cli.run`（任意 lark-cli 命令透传，覆盖未封装 SDK 的 API）
- [x] 工具调用日志：每次 tool call 记录工具名、参数、结果
- [x] `main.py` 集成：启动时初始化 Feishu 客户端，注册全部工具到全局 `tool_provider`

### Agent Executor (`ai/agent.py`)

- [x] LiteLLM + tool-use 执行循环（max_iterations 限制、超时控制）
- [x] ToolProvider 工具 → LiteLLM function calling 格式转换
- [x] 审计日志：每次工具调用记录到 agent 日志
- [x] bugfix: assistant 消息（含 tool_calls）必须在 tool result 之前追加到 messages
- [x] 模型能力校验：validate_model() 检查配置模型是否支持 tool calling
- [x] Provider 感知：自动检测 api_mode，选择对应 Transport 归一化响应
- [x] Reasoning 支持：自动识别 reasoning 模型并注入 reasoning 配置

### Transport 层 (`ai/transports/`)

- [x] `ProviderTransport` 抽象基类：convert_messages / convert_tools / build_kwargs / normalize_response
- [x] `ChatCompletionsTransport`：OpenAI 兼容格式（默认，覆盖 OpenRouter/DeepSeek/Qwen/Ollama/Groq 等）
- [x] `NormalizedResponse` / `ToolCall` / `Usage` 共享类型：统一多 provider 响应格式
- [x] Transport 注册表：get_transport(api_mode) 自动选择

### Model Registry (`ai/model_registry.py`)

- [x] `ProviderEntry` 数据类：provider 定义（slug、label、auth_type、env_vars、api_mode、base_url）
- [x] `ModelInfo` 数据类：模型元数据（tool_call、reasoning、vision、context_window、cost）
- [x] Provider 别名映射：PROVIDER_ALIASES（glm→zai、github→copilot 等 30+ 别名）
- [x] LiteLLM 集成映射：LITELLM_PROVIDER_MAP / LITELLM_ENV_MAP / LITELLM_BASE_URL_OVERRIDES
- [x] 模型能力查询：get_model_capabilities() / supports_reasoning() / detect_api_mode()
- [x] models.dev 元数据丰富：在线拉取 + 磁盘缓存回退

### 数据与路由 (`ai/models.py`)

- [x] `AgentTask` / `AgentResult` 数据类
- [x] `MODEL_ROUTING`：fast / smart / reasoning 三级模型路由（支持环境变量覆盖）

### Skills 系统 (`ai/skills/`)

- [x] 插件式 `Skill` 注册 + `SkillRegistry` 全局注册表
- [x] 触发器匹配：子字符串 + 正则混合，按注册顺序优先
- [x] `skill.apply()`：自动注入 prompt、allowed_tools、complexity 到 AgentTask
- [x] `registry.build_task()`：自动匹配或显式指定 skill，一键构建 AgentTask
- [x] SKILL.md 文件驱动自动发现：`registry.discover_from_dir()` 扫描 skills 目录
- [x] 内置 lark-* skills：lark-approval、lark-attendance、lark-base、lark-calendar、lark-contact、lark-doc、lark-drive、lark-event、lark-im、lark-mail、lark-minutes、lark-okr、lark-openapi-explorer、lark-sheets、lark-skill-maker、lark-slides、lark-task 等 17 个飞书能力 skill
- [x] AgentExecutor 集成：`_build_system_prompt()` 自动查阅 registry
- [x] 旧 `prompts.py` 保持向后兼容

### 配置扩展

- [x] `config/settings.py`：`AgentConfig`（provider、api_mode、模型、工具集、max_iterations、超时）
- [x] `config.example.yaml`：agent 配置段（含 provider、api_mode 字段）
- [x] `main.py`：ToolProvider 初始化 + Feishu 客户端启动

### 验证

- [x] `scripts/verify_agent.py`：配置 + 数据类 + 导入 + AgentExecutor + 真实 LLM → 23/23 通过
- [x] Agent + skills 集成：skill prompt 加载、context 变量插值、工具约束识别 → 通过
- [x] lark-cli 自动安装：`teamflow run` 启动时检查 + 引导安装（`setup/cli.py`）

> Agent 基础设施全部完成。M2 就绪。

---

## M2：飞书工作空间可用

目标：项目创建后自动初始化飞书协作空间。多步编排走 Agent 智能通道，单步确认走确定性通道。

### 编排层改造

- [x] 监听 `project.created` 事件（EventBus.subscribe_global 全局注册）
- [x] 校验 `project.created` 幂等键
- [x] 读取项目基础信息
- [x] 构建 Agent 任务描述：项目名、管理员 open_id、初始化清单

### Agent 执行：工作空间初始化

- [x] Agent 任务：创建群 + 拉人 + 创建文档 + 发欢迎语
- [x] Agent 上下文注入：项目信息、管理员信息
- [x] Agent 处理部分失败：某步失败不阻断后续，收集所有结果
- [x] Agent 结果解析：提取群 ID、群链接、文档 URL
- [x] 文档协作者添加：`drive.v1.permission.add_collaborator` 将管理员添加为文档协作者
- [x] 文档所有权转交：`drive.v1.permission.transfer_owner` 将文档转交给管理员

### 确定性通道：结果回写与通知

- [x] 群 ID、群链接、文档 URL、初始化状态写回项目记录
- [x] 向管理员发送初始化结果回执（确定性通道：send_card）
- [x] 发布 `project.workspace_initialized` 事件

### 进度追踪

- [x] 分步进度卡片：workspace_init_result_card() 展示每步执行状态
- [x] 实时卡片更新：每步完成后更新同一张卡片（update_card_message）
- [x] 表单提交进度同步：ProjectFormSubmission 与 workspace init 共享进度卡片
- [x] 降级文本回执：卡片更新失败时降级为纯文本回执

### 异常处理

- [x] 幂等保障：同一项目不重复创建群和文档（workspace_status 检查）
- [x] 单步失败不遮蔽其他已完成结果
- [x] Agent 执行超时或失败 → 降级为分步确定性通道执行
- [x] 回执发送失败 → 记录日志，可补偿
- [x] 文档权限转交失败 → 降级为添加协作者，不阻断流程

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

- [ ] 工具集扩展：启用 `lark_cli.run` 透传 calendar/task/sheet 等 API
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

- [x] `fast`：简单摘要、命令响应、低成本文本（MODEL_ROUTING + 环境变量覆盖已实现）
- [x] `smart`：风险分析、周报、站会摘要（MODEL_ROUTING + 环境变量覆盖已实现）
- [x] `reasoning`：复杂推理、策略生成、多约束判断（MODEL_ROUTING + 环境变量覆盖已实现）
- [ ] 模型层级与业务场景的实际映射和调优

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
- [x] 双通道调度：编排层根据动作复杂度选择确定性/智能通道
- [x] Agent 执行通道：`ai/agent.py` + `ai/tools/`（ToolProvider 直连 lark-oapi SDK）
- [x] Transport 层：`ai/transports/` 多 provider 响应归一化（ChatCompletions + 扩展点）
- [x] Model Registry：`ai/model_registry.py` provider 定义、别名、模型能力查询
- [x] Skills 系统：`ai/skills/` 插件式 Skill 注册 + SKILL.md 文件驱动自动发现
- [x] 执行结果结构化：`CLIResult` 返回 success、output、error、stderr_log
- [x] Agent 结果结构化：`AgentResult` 返回 success、summary、actions
- [ ] CLI 日志解析：解析 CLI stderr 提取结构化信息写入 ActionLog
- [x] Agent 审计日志：记录 Agent 工具调用链和结果（agent.py 内置日志）
- [ ] 进程管理：事件订阅子进程监控和自动重启（Agent 通道零外部进程）

### 数据存储

- [x] ConversationState
- [x] EventLog
- [x] ActionLog
- [x] Project（status + workspace_status 字段，含飞书资源绑定）
- [x] ProjectFormSubmission（卡片表单提交记录，含进度追踪）
- [ ] Member
- [ ] Task
- [ ] Observation
- [ ] Decision

### 日志与审计

- [x] 接入日志
- [ ] 编排日志（含通道选择决策）
- [x] 执行日志（确定性通道）
- [x] Agent 执行日志（智能通道：`agent.py` 内置 tool call 日志 + ToolProvider 调用日志）
- [ ] 调度日志
- [ ] 模型调用摘要日志（LiteLLM 自带日志可用）
- [ ] 审计记录：项目创建、空间初始化、高风险建议、用户审批、自动执行、配置变更
- [ ] 日志脱敏：密钥、令牌、API Key 不入日志

### 健康检查

- [x] 轻量健康检查：服务存活
- [ ] 详细健康检查：数据库、飞书连接、调度器、模型配置
- [ ] 配置缺失时健康检查暴露明确错误

### 配置管理

- [x] 飞书配置独立管理
- [x] 模型配置独立管理（AgentConfig.provider/api_mode/fast_model/smart_model/reasoning_model + 环境变量覆盖）
- [x] Agent 配置独立管理（AgentConfig: max_iterations, mcp_tools, timeout_seconds）
- [ ] 调度配置独立管理
- [x] 环境变量 + 配置文件双支持（TEAMFLOW_FAST_MODEL 等 + config.yaml）

验收依据：`docs/prd/modules/05-platform-and-observability.md`。

---

## 发布前阻断项

- [x] 飞书消息收发链路可用
- [x] 项目创建成功后能落库
- [x] Agent 能通过 ToolProvider 调用飞书 API（10+ 工具已注册，lark-oapi SDK 直连，`verify_agent.py` 23/23 通过）
- [x] 重复事件不会创建重复群或重复文档（M2 编排幂等逻辑）
- [x] 初始化失败有用户可见反馈（M2 回执消息 + 进度卡片）
- [x] Agent 工具调用链有日志和审计记录（agent.py + ToolProvider 双重日志）
- [ ] 日志中没有密钥或访问令牌
- [ ] 高风险动作不会绕过审批直接执行
- [x] Agent 执行有 max_iterations 上限防止无限循环

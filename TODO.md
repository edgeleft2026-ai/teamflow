# TeamFlow 开发路线 TODO

本 TODO 与 `docs/prd/` 下的 PRD 保持一致。开发时优先按 M0 到 M4 顺序推进，避免在主链路稳定前提前扩展复杂能力。

## M0：飞书交互链路打通

目标：验证飞书消息能收能发，是所有后续功能的地基。

### CLI 基础设施

- [ ] 编译 teamflow-cli：基于 lark-cli 源码，注入 Credential 和 Transport 扩展
- [ ] 实现 Credential Extension：从 TeamFlow 配置读取 App ID / App Secret
- [ ] 实现 Transport Extension：拦截请求/响应，输出结构化 ActionLog 日志
- [ ] 验证 CLI 基础命令可用：`teamflow-cli im +messages-send --help`

### 事件接入

- [ ] 启动 `teamflow-cli event +subscribe` 长驻进程
- [ ] 配置事件类型：`im.message.receive_v1` 等
- [ ] 实现文件监听：watch output-dir 中的 NDJSON 事件文件
- [ ] 飞书原始事件去重
- [ ] Bot 自身消息过滤，避免消息循环

### 消息处理

- [ ] 私聊消息接收与解析
- [ ] 群消息接收与解析：仅响应 @Bot 或明确命令
- [ ] 从消息上下文提取用户 open_id

### 消息发送

- [ ] 封装 `execution.send_message(chat_id, text)` → subprocess 调用 `im +messages-send`
- [ ] 主动发送私聊消息
- [ ] 主动发送群消息

### 运维

- [ ] 接入日志：记录消息进入、解析结果、忽略原因
- [ ] `/health` 轻量健康检查
- [ ] 端到端验证：用户发消息 -> 服务收到 -> 服务回复消息

验收依据：`docs/prd/03-acceptance-checklist.md` 的 M0 部分。

---

## M1：项目创建可用

目标：用户能在飞书中发起项目创建，完成信息收集、项目落库、管理员绑定和创建结果回执。

- [ ] 欢迎引导消息：首次触达或 `/help` 时展示可用能力
- [ ] “开始创建项目”触发识别
- [ ] 分步信息收集状态机
  - [ ] `idle` -> `collecting_project_name`
  - [ ] `collecting_project_name` -> `collecting_repo`
  - [ ] `collecting_repo` -> `creating_project`
  - [ ] `creating_project` -> `created` / `failed`
- [ ] 会话状态持久化：保存 open_id、chat_id、flow、state、payload、expires_at
- [ ] 项目名称收集与校验：非空
- [ ] Git 仓库地址或本地路径收集与校验：非空
- [ ] 项目记录写入数据库：id、name、git_repo_path、admin_open_id、status、created_at、updated_at
- [ ] 管理员绑定：从消息上下文获取 open_id
- [ ] 创建成功回执：项目 ID、项目名、后续初始化提示
- [ ] 创建失败回执：失败步骤、原因、可执行下一步
- [ ] 发布 `project.created` 事件
- [ ] 事件写入 `EventLog`，包含 idempotency_key
- [ ] 动作写入 `ActionLog`
- [ ] 异常处理
  - [ ] 用户中途退出 -> 提示当前阶段
  - [ ] 重复触发创建 -> 允许重新开始或覆盖旧流程
  - [ ] 输入为空 -> 提示重新输入
  - [ ] 飞书身份解析失败 -> 明确报错并记录日志

验收依据：`docs/prd/modules/01-project-entry-and-onboarding.md`。

---

## M2：飞书工作空间可用

目标：项目创建后自动初始化飞书协作空间，管理员收到完整回执。

- [ ] 监听 `project.created` 事件
- [ ] 校验 `project.created` 幂等键
- [ ] 读取项目基础信息
- [ ] 创建或复用飞书项目群：`TeamFlow | {项目名}`（`im +chat-create`）
- [ ] 拉管理员入群（`im +chat-members-add`）
- [ ] 获取群分享链接（`im +chat-link`）
- [ ] 创建或复用项目文档（`docs +create`）
- [ ] 项目文档包含项目名称、负责人、仓库信息、创建时间
- [ ] 群 ID、群链接、文档 URL、初始化状态写回项目记录
- [ ] 向管理员发送初始化结果回执：每步成功或失败状态
- [ ] 在项目群发送欢迎消息：群用途、项目名、可用指令、文档链接
- [ ] 发布 `project.workspace_initialized` 事件
- [ ] 幂等保障：同一项目不重复创建群和文档
- [ ] 单步失败不遮蔽其他已完成结果
- [ ] 异常处理
  - [ ] 群创建失败 -> 显式失败并记录原因
  - [ ] 拉人失败 -> 回执中说明
  - [ ] 文档创建失败 -> 保留群结果并说明
  - [ ] 回执发送失败 -> 记录日志，可补偿
  - [ ] 数据写回失败 -> 记录日志，避免重复创建外部资源

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

### 3.2 提醒能力

- [ ] 逾期提醒：任务过截止时间且未完成
- [ ] 阻塞提醒：任务被标记阻塞或存在阻塞原因
- [ ] 停滞提醒：任务或分支长时间无更新
- [ ] 成员负载提醒：成员负载显著高于团队平均
- [ ] 提醒消息去重与聚合
- [ ] 提醒写入 Observation

### 3.3 报告能力

- [ ] 每日站会摘要：昨日完成、进行中、需关注、健康度、今日建议、数据缺口
- [ ] 每周周报：本周概要、关键成果、进行中、风险问题、下周计划、贡献统计、数据缺口
- [ ] 风险分析报告：整体风险、进度风险、人员风险、技术风险、关键风险项、建议行动、事实依据

### 3.4 查询能力

- [ ] `/help`
- [ ] `/status`
- [ ] `/tasks`
- [ ] `/risk`
- [ ] `/standup`
- [ ] `/report`
- [ ] 私聊多项目场景提示用户指定项目
- [ ] 数据为空时返回空状态说明

### 3.5 消息路由与调度

- [ ] 群通知：公开项目协作信息
- [ ] 管理员私聊：结果回执和重点提醒
- [ ] 高价值风险同时发群和私聊
- [ ] 每日站会摘要定时触发
- [ ] 每周周报定时触发
- [ ] 逾期任务定时扫描
- [ ] 停滞任务定时扫描
- [ ] Git 活动定时扫描

验收依据：`docs/prd/modules/03-project-operations-and-collaboration.md`。

---

## M4：AI 能力增强

目标：在规则和策略基础上叠加 AI 分析，实现更智能的风险判断、建议生成和受控自动决策。

### 4.1 分层决策机制

- [ ] 规则层：高确定性事件直接处理
- [ ] 策略层：模板化场景策略匹配
- [ ] AI 分析层：复杂风险归因、周报总结、自然语言问答
- [ ] 决策结果写入 Decision

### 4.2 自治级别控制

- [ ] `auto`：通知、汇总、提醒、写入观察记录
- [ ] `approval`：重分配任务、更改优先级、更新重要文档
- [ ] `forbidden`：删除数据、移除成员、关闭项目、修改审计记录

### 4.3 提示词体系

- [ ] 系统角色提示词
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

- [ ] 三层架构：接入层 -> 业务编排层 -> 执行层
- [ ] Python 执行层封装：`execution` 模块统一封装 teamflow-cli subprocess 调用
- [ ] CLI 命令映射：每个业务动作对应具体 CLI 命令和参数
- [ ] 执行结果结构化：解析 CLI stdout JSON → success、action_name、target、output、error_message
- [ ] Transport Extension 自动记录 ActionLog：解析 CLI stderr 结构化日志
- [ ] CLI 进程管理：短命令同步调用，事件订阅长驻进程监控和自动重启

### 数据存储

- [ ] Project
- [ ] Member
- [ ] Task
- [ ] ConversationState
- [ ] EventLog
- [ ] ActionLog
- [ ] Observation
- [ ] Decision

### 日志与审计

- [ ] 接入日志
- [ ] 编排日志
- [ ] 执行日志
- [ ] 调度日志
- [ ] 模型调用摘要日志
- [ ] 审计记录：项目创建、空间初始化、高风险建议、用户审批、自动执行、配置变更
- [ ] 日志脱敏：密钥、令牌、API Key 不入日志

### 健康检查

- [ ] 轻量健康检查：服务存活
- [ ] 详细健康检查：数据库、飞书连接、调度器、模型配置
- [ ] 配置缺失时健康检查暴露明确错误

### 配置管理

- [ ] 飞书配置独立管理
- [ ] 模型配置独立管理
- [ ] 调度配置独立管理
- [ ] 环境变量 + 配置文件双支持

验收依据：`docs/prd/modules/05-platform-and-observability.md`。

---

## 发布前阻断项

- [ ] 飞书消息收发链路可用
- [ ] 项目创建成功后能落库
- [ ] 重复事件不会创建重复群或重复文档
- [ ] 初始化失败有用户可见反馈
- [ ] 关键动作都有日志和审计记录
- [ ] 日志中没有密钥或访问令牌
- [ ] 高风险动作不会绕过审批直接执行

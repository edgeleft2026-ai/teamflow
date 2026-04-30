# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TeamFlow 是一个运行在飞书场景中的 AI 项目协作助手。核心主链路：用户在飞书中发起项目 → 系统完成创建和协作空间初始化 → 围绕项目提供提醒、汇报和查询。M0+M1 已完成（消息收发、项目创建），当前推进 Agent 基础设施建设。

## 开发命令

项目使用 Python 3.11+，虚拟环境位于 `.venv/`，以 editable 模式安装。

```bash
# 安装项目（editable + dev 依赖）
pip install -e ".[dev,setup]"

# 运行应用
teamflow run           # 启动主事件循环
teamflow setup         # 交互式设置向导（QR 扫码或手动输入凭证）
teamflow reset         # 删除 config.yaml、数据库和临时文件

# 测试（暂无测试文件；测试目录 src/tests/ 尚未创建）
pytest                 # asyncio_mode = "auto"，测试路径 src/tests/

# 代码检查
ruff check src/
```

### 外部依赖

- **lark-cli**：Go 二进制，通过 npm 安装。确定性通道通过 subprocess 调用，凭证通过环境变量注入。`teamflow setup` 会自动安装。
- **Node.js LTS**：用于运行 `@larksuiteoapi/lark-mcp` MCP Server（Agent 通道需要，尚未集成）。

## 技术选型

双通道架构：**Python 主进程**（业务编排 + AI Agent）+ **双执行层**（确定性通道：lark-cli subprocess；智能通道：Agent + MCP）。

| 层 | 技术 | 理由 |
|---|---|---|
| 业务编排 | Python 3.12+, asyncio | AI 生态成熟、迭代快 |
| 数据库 | SQLModel + SQLite | 类型安全、零运维 |
| AI 调用 | LiteLLM + 自建 tool-use 循环 | 统一多模型接口、模型无关 |
| Agent 工具 | `@larksuiteoapi/lark-mcp`（飞书官方 MCP Server） | 全量 OpenAPI、动态工具发现 |
| MCP 客户端 | Python `mcp` SDK | 官方 MCP 协议实现 |
| 调度 | APScheduler | 轻量 cron/interval |
| 确定性执行层 | lark-cli (Go subprocess) | 高频确定性动作：发消息、拉人、事件订阅 |
| 凭证管理 | Python 环境变量注入 + MCP 启动参数 | 确定性通道走环境变量，Agent 通道走 `-a/-s` 启动参数 |
| 请求追踪 | stderr 捕获 + Agent 审计日志 | 双通道分别追踪 |
| 事件订阅 | `lark-cli event +subscribe` | WebSocket + NDJSON 输出 |

完整技术架构见 `docs/prd/06-technical-architecture.md`。

## 仓库结构

```
teamflow/
├── docs/prd/              # 产品需求文档
│   ├── 00-product-overview.md   # 产品总纲
│   ├── 01-mvp-scope.md         # MVP 范围：M0-M4 交付边界
│   ├── 02-data-and-event-model.md  # 核心数据对象、状态枚举、事件 payload
│   ├── 03-acceptance-checklist.md   # 按里程碑的验收项
│   ├── 04-testing-strategy.md   # 测试分层和验证方式
│   ├── 05-prompt-templates.md   # AI 提示词模板
│   ├── 06-technical-architecture.md  # 技术架构：混合架构、CLI 集成
│   └── modules/                 # 五个模块的详细 PRD
├── cli/                   # lark-cli 源码（参考学习，不直接引用）
├── src/
│   ├── teamflow/          # Python 主进程源码
│   │   ├── core/          # 领域模型（StrEnum 枚举）
│   │   ├── access/        # 接入层：NDJSON 事件解析、事件去重分发、卡片回调
│   │   ├── orchestration/ # 编排层：CommandRouter、ProjectCreateFlow 状态机、EventBus、卡片模板
│   │   ├── execution/     # 确定性执行层（lark-cli subprocess 封装）
│   │   ├── ai/            # AI 层：ToolProvider（Python 原生工具）、Agent Executor、Skills、模型路由
│   │   ├── scheduling/    # 调度层（空桩，待实现）
│   │   ├── storage/       # 数据层：SQLite 初始化、SQLModel 模型、Repository
│   │   ├── setup/         # 设置向导：QR 注册、凭证验证
│   │   ├── config/        # 配置管理：Pydantic 模型 + YAML 加载
│   │   ├── __main__.py    # CLI 入口：teamflow setup/run/reset 子命令
│   │   └── main.py        # 核心 async main()：初始化 DB、启动订阅进程、事件循环
│   └── tests/             # 测试（目录和文件尚未创建）
├── hermes-agent/          # 参考实现（不直接引用）
├── config.example.yaml    # 配置示例
└── TODO.md                # 开发路线清单（按 M0→M4 排列，标记完成状态）
```

## 核心源文件

**启动与入口：**
- `src/teamflow/__main__.py` — CLI 入口：`teamflow setup`（设置向导）、`teamflow run`（启动主循环）、`teamflow reset`（清理数据）
- `src/teamflow/main.py` — 核心异步主循环：加载配置 → 初始化数据库 → 启动 lark-cli 事件订阅子进程 → 卡片回调 WebSocket → EventFileWatcher → EventDispatcher → 健康检查 HTTP server（`127.0.0.1:9090/health`）

**接入层 (`access/`)：**
- `parser.py` — `FeishuEvent`/`CardActionData` 数据类，NDJSON 解析、bot 消息过滤、字段提取
- `watcher.py` — `EventFileWatcher`：轮询 NDJSON 文件目录，跟踪文件偏移，新行回调
- `dispatcher.py` — `EventDispatcher`：按事件类型注册 handler，event_id 内存去重（上限 10000）
- `callback.py` — 基于 `lark-oapi` SDK 的 WebSocket 客户端，接收卡片交互回调，路由到 `CommandRouter`

**编排层 (`orchestration/`)：**
- `command_router.py` — `CommandRouter`：文本消息路由（help/创建项目 触发词），会话状态恢复
- `project_flow.py` — `ProjectCreateFlow`：3 状态状态机（collecting_project_name → collecting_repo → creating_project），支持文本对话和卡片表单
- `event_bus.py` — `EventBus`：内部发布/订阅，idempotency_key 去重，EventLog 持久化
- `card_templates.py` — 飞书卡片 JSON 模板工厂：welcome、project_created、project_create_form、project_failed

**执行层 (`execution/`)：**
- `cli.py` — `CLIResult` 数据类、`find_cli_binary()`、tenant_access_token 缓存交换（提前 60s 刷新）、`run_cli()` subprocess 封装
- `messages.py` — 便捷发送函数：`send_text()`、`send_card()`、`send_markdown()`、`create_chat()`、`add_chat_members()`

**数据层 (`storage/`)：**
- `models.py` — 四个 SQLModel 表：`Project`、`ConversationState`、`EventLog`、`ActionLog`（全部 UUID 主键、UTC 时间戳）
- `repository.py` — 四个 Repository 类：`ProjectRepo`、`ConversationStateRepo`、`EventLogRepo`、`ActionLogRepo`
- `database.py` — `init_db()`（SQLite，路径 `data/teamflow.db` 或 `TEAMFLOW_DB_PATH` 环境变量）、`get_session()` 上下文管理器

**配置 (`config/`)：**
- `settings.py` — Pydantic `FeishuConfig`（app_id、app_secret、brand、admin_open_id）和 `TeamFlowConfig`。`load_config()` 从 `config.yaml` 加载，支持环境变量覆盖。

**设置向导 (`setup/`)：**
- `cli.py` — 交互式 CLI：检查 lark-cli → 可选 npm 安装 → QR 注册或手动输入凭证 → 写入 config.yaml
- `feishu.py` — 飞书 OAuth device-code 流程：`qr_register()` 自动创建应用，`probe_bot()` 验证凭证

**`ai/`** — Agent 智能通道（Agent 基础设施已实现，端到端验证待真实凭证）：
- `models.py` — `AgentTask`/`AgentResult` 数据类 + `MODEL_ROUTING` 模型路由配置
- `tools/` — `ToolProvider`：注册 Python 异步函数为 Agent 工具（零外部进程），含飞书 API 工具（`feishu.py`）
- `agent.py` — `AgentExecutor`：LiteLLM tool-use 循环（系统提示词 → LLM → 工具调用 → 追加结果 → 循环直到完成或 max_iterations）
- `prompts.py` — 系统提示词管理（`WORKSPACE_INIT_PROMPT` 等，向后兼容）
- `skills/` — Agent 技能系统：插件式 `Skill` 注册 + `SkillRegistry` 全局注册表，支持触发器匹配（子字符串/正则），`workspace_init` 技能已内置

**`scheduling/`** 包当前只有空的 `__init__.py`，尚未实现。

## 架构设计

三层架构 + 双通道执行，严格单向依赖：

```
Python 主进程
├── 接入层 — 消费 CLI 事件订阅进程的 NDJSON 输出、指令解析、消息路由
├── 业务编排层 — 状态机、事件分发、流程编排、双通道调度（不直接调用飞书 API）
├── AI 层 — LiteLLM tool-use 循环、MCP 客户端、提示词管理、降级策略（待实现）
│
│  双通道执行 ↓
│
├── 确定性通道 (lark-cli, 预编译 Go 二进制)
│   ├── Python 执行层封装 — subprocess 调用，环境变量注入凭证
│   ├── CLI 日志捕获 — stderr 结构化日志解析
│   └── 事件订阅 — 长驻进程 WebSocket → NDJSON → 文件输出
│
└── 智能通道 (Agent + @larksuiteoapi/lark-mcp MCP Server)（待实现）
    ├── MCP Client (Python mcp SDK, stdio transport)
    └── Agent executor — LiteLLM tool-use 循环，动态发现和调用飞书工具
```

关键约束：
- 简单确定性动作（发消息、拉人入群）走确定性通道，复杂多步编排走 Agent 智能通道
- 编排层根据动作复杂度选择执行通道，默认确定性通道
- Agent 通过 MCP 协议动态发现飞书工具，不硬编码命令映射
- Agent 设置 max_iterations 防止无限循环，高风险动作不加入 Agent 工具集

## 核心业务概念

### 数据对象

Project、Member、Task、ConversationState、EventLog、ActionLog、Observation、Decision。完整字段定义见 `docs/prd/02-data-and-event-model.md`。

### 关键状态枚举（定义于 `src/teamflow/core/enums.py`）

- **Project.status**: `creating` → `created` → `initializing_workspace` → `active` / `failed` / `archived`
- **WorkspaceStatus**: `pending` → `running` → `succeeded` / `partial_failed` / `failed`
- **EventStatus**: `pending` / `processing` / `succeeded` / `failed` / `ignored`
- **ActionResult**: `success` / `failure`

### 事件驱动

所有内部事件必须带 `idempotency_key`。核心事件：`project.created`、`project.workspace_initialized`、`task.overdue`、`task.blocked`、`task.stale`、`schedule.daily_standup`、`schedule.weekly_report`。

### AI 模型层级（规划中，尚未实现）

- `fast`：简单摘要、命令响应
- `smart`：风险分析、周报、站会摘要
- `reasoning`：复杂推理、策略生成

## 里程碑

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M0 | 飞书交互链路打通 | 已完成 |
| M1 | 项目创建可用 | 已完成 |
| Agent 基础设施 | MCP Server/Client、Agent Executor | 未开始 |
| M2 | 飞书工作空间初始化 | 未开始 |
| M3 | 项目运行与协作 | 未开始 |
| M4 | AI 能力增强 | 未开始 |

开发时必须按 M0→M4 顺序推进，验收标准见 `docs/prd/03-acceptance-checklist.md`。`TODO.md` 中有逐项完成状态的详细清单。

## 产品原则（开发决策依据）

1. **稳定优先**：主链路可用先于交互复杂度
2. **闭环优先**：每个动作有明确输入、结果和反馈
3. **飞书优先**：核心体验聚焦飞书
4. **数据优先**：分析建议必须基于项目数据，无数据时明确说明
5. **可追踪优先**：关键动作可定位、可审计、可解释
6. **渐进智能**：规则化先于 AI 能力
7. **人可接管**：高风险动作必须支持人工确认或拒绝

## 关键约束

- 幂等：飞书事件用 `event_id` 去重，业务事件用 `idempotency_key`，外部资源创建前先检查已有绑定
- 脱敏：App Secret、访问令牌、模型 API Key 不得写入日志或业务表
- 单步失败隔离：部分步骤失败不遮蔽已成功结果，不回滚已创建的外部资源
- 定时调度幂等：以项目 ID + 日期/周编号作为幂等维度，多实例部署不重复执行
- 数据库文件 `data/teamflow.db` 由 SQLite 自动创建，路径可通过 `TEAMFLOW_DB_PATH` 环境变量覆盖
- 事件订阅进程 `lark-cli event +subscribe` 为长驻子进程，main.py 主循环监控其存活状态
- 卡片回调通过 `lark-oapi` SDK 的 WebSocket 客户端在独立 daemon 线程中接收

## cli 子目录

`cli/` 是飞书官方 CLI (lark-cli) 源码，仅供学习参考，不直接引用。TeamFlow 使用预编译的 lark-cli 二进制，通过 Python 执行层（`src/teamflow/execution/cli.py`）封装 subprocess 调用。值得关注的设计模式：

- `extension/credential/` — 凭证扩展接口（`credential.Provider`）
- `extension/transport/` — 传输扩展接口（`transport.Provider` + `transport.Interceptor`）
- `shortcuts/` — 200+ 业务命令实现，每个 shortcut 包含 Validate/DryRun/Execute
- `shortcuts/register.go` — 命令注册入口

## hermes-agent 子目录

`hermes-agent/` 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的参考实现。该目录有自己独立的 `AGENTS.md`。

可参考的架构模式：
- `gateway/platforms/feishu.py` — 飞书平台适配器
- `tools/registry.py` — 工具注册与发现机制

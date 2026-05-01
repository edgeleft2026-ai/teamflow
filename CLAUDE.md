# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TeamFlow 是一个运行在飞书场景中的 AI 项目协作助手。核心主链路：用户在飞书中发起项目 → 系统完成创建和协作空间初始化 → 围绕项目提供提醒、汇报和查询。M0+M1+M2+Agent 基础设施已完成，Gitea 权限同步已部分实现，当前推进 M3（项目运行与协作）。

## 开发命令

```bash
pip install -e ".[dev,setup]"   # 安装（editable + dev 依赖）
teamflow run                    # 启动主事件循环
teamflow setup                  # 交互式设置向导（QR 扫码或手动输入凭证）
teamflow reset                  # 删除 config.yaml、数据库和临时文件
pytest                          # asyncio_mode = "auto"，测试路径 src/tests/
pytest -k <test_name>           # 运行单个测试（按名称匹配）
pytest src/tests/test_file.py::test_func  # 运行指定测试函数
ruff check src/                 # 代码检查（target py312, line-length 100）
ruff format src/                # 代码格式化
```

外部依赖：**lark-cli**（Go 二进制，通过 npm 安装，`teamflow setup` 会自动引导安装；也可从 `cli/` 源码编译：`cd cli && go build -o lark-cli`）、**Node.js LTS**（MCP Server 用，尚未集成）。

验证脚本：`scripts/verify_agent.py`（Agent + ToolProvider 端到端验证，需配置真实 LLM），`scripts/e2e_test.py`（完整业务流程 E2E 测试，自动创建并清理飞书/Gitea 资源）。

## 技术架构

双通道架构：**Python 主进程**（业务编排 + AI Agent）+ **双执行层**。

```
Python 主进程
├── 接入层 (access/) — 消费 lark-cli 事件订阅的 NDJSON 输出、指令解析、消息路由、卡片回调
│   ├── parser.py — NDJSON 事件解析（FeishuEvent/CardActionData/ChatMemberEventData）
│   ├── dispatcher.py — 事件分发 + event_id 去重
│   ├── watcher.py — 文件系统轮询监听事件输出
│   ├── callback.py — lark-oapi WebSocket 卡片回调客户端
│   └── feishu_contact.py — 飞书通讯录服务（用户查询/卡片发送）
├── 编排层 (orchestration/) — 状态机、事件分发、流程编排（不直接调用飞书 API）
├── AI 层 (ai/) — LiteLLM tool-use 循环、ToolProvider、Skills、模型路由
│
│  双通道执行 ↓
│
├── 确定性通道 (execution/) — lark-cli subprocess 封装
│   ├── 凭证通过环境变量注入，tenant_access_token 自动交换（提前 60s 刷新）
│   ├── 事件订阅长驻进程：lark-cli event +subscribe → WebSocket → NDJSON → 文件输出
│   └── 便捷函数：send_text/send_card/send_markdown/create_chat/add_chat_members
│
└── 智能通道 (ai/) — Agent + ToolProvider（Python 原生，lark-oapi SDK 直连）
    ├── ToolProvider：注册 Python 异步函数为 Agent 工具（零外部进程）
    ├── 当前 10+ 飞书工具：im.v1.chat.*、im.v1.message.create、docx.v1.document.create、
    │   drive.v1.permission.*、im.v1.bot.info、lark_cli.run
    ├── Transport 层 (`ai/transports/`)：多 Provider 响应归一化（ChatCompletions + 扩展点）
    ├── Model Registry (`ai/model_registry.py`)：Provider 定义、别名映射、模型能力查询
    └── Skills 系统：插件式注册 + SKILL.md 文件驱动自动发现，17 个飞书能力 skill 已内置
```

**设计决策**：最初采用 MCP 协议（`@larksuiteoapi/lark-mcp` MCP Server + Python `mcp` SDK），因飞书 MCP Server v0.5.1 协议不兼容，改为 ToolProvider（lark-oapi SDK 直连）。AgentExecutor 接口保持不变，MCP 方案待飞书官方更新后可平滑切换。

### 关键架构约束

- 编排层根据动作复杂度选择通道，默认确定性通道；复杂多步编排走 Agent
- 简单确定性动作（发消息、拉人）走确定性通道，不经过 Agent
- Agent 设置 max_iterations 防止无限循环，高风险动作不加入工具集
- 三层单向依赖：接入层 → 编排层 → 执行层，不允许反向调用

### 数据层 (`storage/`)

SQLite（路径 `data/teamflow.db` 或 `TEAMFLOW_DB_PATH` 环境变量）+ SQLModel。核心表：`Project`、`ConversationState`、`EventLog`、`ActionLog`、`ProjectFormSubmission`、`UserIdentityBinding`、`ProjectAccessBinding`、`ProjectMember`（全部 UUID 主键、UTC 时间戳），对应 Repository 在 `storage/repository.py`（单数）。

### 配置 (`config/`)

Pydantic 模型 + YAML 加载（`config.yaml`）+ 环境变量覆盖（`.env` 文件自动加载）。支持四大配置段：
- `FeishuConfig`（app_id/secret/brand/admin_open_id）— 敏感字段通过 `FEISHU_APP_ID`/`FEISHU_APP_SECRET` 等环境变量注入
- `AgentConfig`（provider/api_mode/模型/工具集/max_iterations/超时）
- `GiteaConfig`（base_url/access_token/default_private/auto_create/org_name）— access_token 通过 `GITEA_ACCESS_TOKEN` 环境变量注入
- `LoggingConfig`（level/log_dir/file_enabled/json_format/color/module_levels）

配置优先级：环境变量 > YAML 文件 > 模型默认值。`.env.example` 为模板文件，复制为 `.env` 后填入凭据。
敏感字段（app_secret、access_token、API keys）必须在 `.env` 中配置，不可写入 `config.yaml`。

### Agent 模型路由 (`ai/models.py`)

三级模型路由，可通过环境变量覆盖：`fast`（简单摘要）→ `smart`（分析报告）→ `reasoning`（复杂推理）。

### 日志系统 (`core/logging.py`)

生产级日志：Console + RotatingFile 双输出、敏感字段自动脱敏（app_secret/access_token 等）、JSON 格式化支持（便于 ELK/Loki 聚合）、correlation_id 上下文追踪、按模块独立日志级别配置。统一使用 `get_logger(__name__)` 获取 logger。

### 关键状态枚举 (`core/enums.py`)

- **ProjectStatus**: `creating` → `created` → `initializing_workspace` → `active` / `failed` / `archived`
- **WorkspaceStatus**: `pending` → `running` → `succeeded` / `partial_failed` / `failed`
- **EventStatus**: `pending` / `processing` / `succeeded` / `failed` / `ignored`
- **MemberRole**: `admin` / `developer` / `viewer`
- **MemberStatus**: `active` / `removed`

### 事件驱动

所有内部事件必须带 `idempotency_key`。核心事件：`project.created`、`project.workspace_initialized`、`task.overdue`、`task.blocked`、`task.stale`、`schedule.daily_standup`、`schedule.weekly_report`。

飞书群成员变更事件（`im.chat.member.user.added_v1` / `deleted_v1`）触发 Gitea 权限同步，由 `orchestration/access_sync.py` 处理。

### Gitea 权限同步 (`git/` + `orchestration/access_sync.py`)

项目创建时自动在 Gitea Organization 下创建仓库和 Team，并将 Team 与仓库绑定。飞书群成员进出事件自动同步到 Gitea Team 成员：

```
Feishu Group Member
  -> TeamFlow Project (ProjectAccessBinding)
  -> Gitea Team
  -> Gitea Repository Permission
```

身份映射通过 `UserIdentityBinding` 表维护（open_id → gitea_username），支持显式绑定和邮箱自动匹配兜底。

## 运行时启动流程

`teamflow run` → 检查 lark-cli → 加载 config → 初始化 DB → 初始化日志 → 向管理员发启动通知 → 启动 lark-cli 事件订阅子进程 → 初始化 ToolProvider（Feishu 客户端）→ 启动卡片回调 WebSocket → 启动 EventFileWatcher → 注册 workspace init 事件处理器 → 注册 access sync 群成员事件处理器 → 健康检查 HTTP（`TEAMFLOW_HEALTH_PORT`，默认 9090）→ 主循环监控子进程存活。

## 里程碑

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M0 | 飞书交互链路打通 | 已完成 |
| M1 | 项目创建可用 | 已完成 |
| M2 | 飞书工作空间初始化 | 已完成 |
| Gitea 权限同步 | 仓库/Team 自动创建、成员权限同步 | 部分完成 |
| Agent 基础设施 | ToolProvider、AgentExecutor、Skills、Transport、Model Registry | 已完成 |
| M3 | 项目运行与协作 | 未开始 |
| M4 | AI 能力增强 | 未开始 |

开发时必须按 M0→M4 顺序推进。验收标准见 `docs/prd/03-acceptance-checklist.md`，逐项清单见 `TODO.md`。

## 产品原则

1. **稳定优先**：主链路可用先于交互复杂度
2. **闭环优先**：每个动作有明确输入、结果和反馈
3. **飞书优先**：核心体验聚焦飞书
4. **数据优先**：分析建议必须基于项目数据，无数据时明确说明
5. **可追踪优先**：关键动作可定位、可审计、可解释
6. **渐进智能**：规则化先于 AI 能力
7. **人可接管**：高风险动作必须支持人工确认或拒绝

## 关键约束

- 幂等：飞书事件用 `event_id` 去重，业务事件用 `idempotency_key`，外部资源创建前先检查已有绑定
- 脱敏：App Secret、访问令牌、模型 API Key 不得写入日志或业务表（日志系统内置 SensitiveFilter 自动脱敏）
- **密钥管理**：敏感凭据（app_secret、access_token、API keys）必须通过 `.env` 文件或环境变量配置，严禁写入 `config.yaml` 或提交到仓库。参见 `.env.example` 模板。
- 单步失败隔离：部分步骤失败不遮蔽已成功结果，不回滚已创建的外部资源
- 定时调度幂等：以项目 ID + 日期/周编号作为幂等维度
- 事件订阅进程 `lark-cli event +subscribe` 为长驻子进程，main.py 监控存活
- 卡片回调通过 `lark-oapi` SDK 的 WebSocket 在独立 daemon 线程中接收
- SQLite 启用 WAL 模式 + busy_timeout(5000ms) + check_same_thread=False 以支持多线程并发

## 参考子目录

- `cli/` — 飞书官方 lark-cli 源码（Go），仅供参考学习，不直接引用。可编译：`cd cli && go build -o lark-cli`
- `hermes-agent/` — Hermes Agent 参考实现，有独立 `AGENTS.md`
- `scripts/` — 验证和测试脚本（verify_agent.py、e2e_test.py 等）

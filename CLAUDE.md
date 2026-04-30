# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TeamFlow 是一个运行在飞书场景中的 AI 项目协作助手。核心主链路：用户在飞书中发起项目 → 系统完成创建和协作空间初始化 → 围绕项目提供提醒、汇报和查询。M0+M1+Agent 基础设施已完成，当前推进 M2（飞书工作空间初始化）。

## 开发命令

```bash
pip install -e ".[dev,setup]"   # 安装（editable + dev 依赖）
teamflow run                    # 启动主事件循环
teamflow setup                  # 交互式设置向导（QR 扫码或手动输入凭证）
teamflow reset                  # 删除 config.yaml、数据库和临时文件
pytest                          # asyncio_mode = "auto"，测试路径 src/tests/
ruff check src/                 # 代码检查
```

外部依赖：**lark-cli**（Go 二进制，通过 npm 安装，`teamflow setup` 会自动引导安装）、**Node.js LTS**（MCP Server 用，尚未集成）。

## 技术架构

双通道架构：**Python 主进程**（业务编排 + AI Agent）+ **双执行层**。

```
Python 主进程
├── 接入层 (access/) — 消费 lark-cli 事件订阅的 NDJSON 输出、指令解析、消息路由、卡片回调
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
    ├── 当前 8 个飞书工具：im.v1.chat.*、im.v1.message.create、docx.v1.document.create、im.v1.bot.info
    └── Skills 系统：插件式注册 + SkillRegistry 触发器匹配，workspace_init 技能已内置
```

**设计决策**：最初采用 MCP 协议（`@larksuiteoapi/lark-mcp` MCP Server + Python `mcp` SDK），因飞书 MCP Server v0.5.1 协议不兼容，改为 ToolProvider（lark-oapi SDK 直连）。AgentExecutor 接口保持不变，MCP 方案待飞书官方更新后可平滑切换。

### 关键架构约束

- 编排层根据动作复杂度选择通道，默认确定性通道；复杂多步编排走 Agent
- 简单确定性动作（发消息、拉人）走确定性通道，不经过 Agent
- Agent 设置 max_iterations 防止无限循环，高风险动作不加入工具集
- 三层单向依赖：接入层 → 编排层 → 执行层，不允许反向调用

### 数据层 (`storage/`)

SQLite（路径 `data/teamflow.db` 或 `TEAMFLOW_DB_PATH` 环境变量）+ SQLModel。四张表：`Project`、`ConversationState`、`EventLog`、`ActionLog`（全部 UUID 主键、UTC 时间戳），各有对应 Repository。

### 配置 (`config/`)

Pydantic 模型 + YAML 加载（`config.yaml`）。`FeishuConfig`（app_id/secret/brand/admin_open_id）+ `AgentConfig`（模型/工具集/max_iterations/超时）。支持环境变量覆盖（`TEAMFLOW_FAST_MODEL` 等）。

### Agent 模型路由 (`ai/models.py`)

三级模型路由，可通过环境变量覆盖：`fast`（简单摘要）→ `smart`（分析报告）→ `reasoning`（复杂推理）。

### 关键状态枚举 (`core/enums.py`)

- **ProjectStatus**: `creating` → `created` → `initializing_workspace` → `active` / `failed` / `archived`
- **WorkspaceStatus**: `pending` → `running` → `succeeded` / `partial_failed` / `failed`
- **EventStatus**: `pending` / `processing` / `succeeded` / `failed` / `ignored`

### 事件驱动

所有内部事件必须带 `idempotency_key`。核心事件：`project.created`、`project.workspace_initialized`、`task.overdue`、`task.blocked`、`task.stale`、`schedule.daily_standup`、`schedule.weekly_report`。

## 运行时启动流程

`teamflow run` → 检查 lark-cli → 加载 config → 初始化 DB → 向管理员发启动通知 → 启动 lark-cli 事件订阅子进程 → 初始化 ToolProvider（Feishu 客户端）→ 启动卡片回调 WebSocket → 启动 EventFileWatcher → 健康检查 HTTP（`TEAMFLOW_HEALTH_PORT`，默认 9090）→ 主循环监控子进程存活。

## 里程碑

| 里程碑 | 目标 | 状态 |
|--------|------|------|
| M0 | 飞书交互链路打通 | 已完成 |
| M1 | 项目创建可用 | 已完成 |
| Agent 基础设施 | ToolProvider、AgentExecutor、Skills | 已完成 |
| M2 | 飞书工作空间初始化 | 未开始 |
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
- 脱敏：App Secret、访问令牌、模型 API Key 不得写入日志或业务表
- 单步失败隔离：部分步骤失败不遮蔽已成功结果，不回滚已创建的外部资源
- 定时调度幂等：以项目 ID + 日期/周编号作为幂等维度
- 事件订阅进程 `lark-cli event +subscribe` 为长驻子进程，main.py 监控存活
- 卡片回调通过 `lark-oapi` SDK 的 WebSocket 在独立 daemon 线程中接收

## 参考子目录

- `cli/` — 飞书官方 lark-cli 源码（Go），仅供参考学习，不直接引用
- `hermes-agent/` — Hermes Agent 参考实现，有独立 `AGENTS.md`

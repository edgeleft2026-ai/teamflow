# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TeamFlow 是一个运行在飞书场景中的 AI 项目协作助手。核心主链路：用户在飞书中发起项目 → 系统完成创建和协作空间初始化 → 围绕项目提供提醒、汇报和查询。项目处于早期规划阶段，当前只有 PRD 文档，尚无业务源代码。

## 技术选型

混合架构：**Python 主进程**（业务编排 + AI）+ **teamflow-cli**（Go，基于 lark-cli 编译的执行层）。

| 层 | 技术 | 理由 |
|---|---|---|
| 业务编排 | Python 3.12+, asyncio | AI 生态成熟、迭代快 |
| 数据库 | SQLModel + SQLite | 类型安全、零运维 |
| AI 调用 | LiteLLM | 统一多模型接口 |
| 调度 | APScheduler | 轻量 cron/interval |
| 执行层 | teamflow-cli (Go subprocess) | 复用 lark-cli 200+ 命令 |
| 凭证管理 | CLI Credential Extension | 从 TeamFlow 配置读取 |
| 请求追踪 | CLI Transport Extension | 自动拦截记录 ActionLog |
| 事件订阅 | `teamflow-cli event +subscribe` | WebSocket + NDJSON 输出 |

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
├── cli/                   # lark-cli 源码（上游，用于编译 teamflow-cli）
├── src/
│   ├── teamflow/          # Python 主进程源码（待建）
│   │   ├── access/        # 接入层
│   │   ├── orchestration/ # 业务编排层
│   │   ├── execution/     # 执行层（CLI subprocess 封装）
│   │   ├── ai/            # AI 层
│   │   ├── scheduling/    # 调度层
│   │   ├── storage/       # 数据层
│   │   └── config/        # 配置管理
│   ├── teamflow-cli/      # 自定义 CLI（Go，含 Credential/Transport 扩展）
│   └── tests/             # 测试
├── hermes-agent/          # Hermes Agent 参考实现
└── TODO.md                # 开发路线清单
```

## 架构设计

三层架构 + 混合语言实现，严格单向依赖：

```
Python 主进程
├── 接入层 — 消费 CLI 事件订阅进程的 NDJSON 输出、指令解析、消息路由
├── 业务编排层 — 状态机、事件分发、流程编排（不直接调用飞书 API）
├── AI 层 — LiteLLM 多模型路由、提示词管理、降级策略
│
│  subprocess ↓
│
└── 执行层 (teamflow-cli, Go)
    ├── Credential Extension — 从 TeamFlow 配置读取飞书凭证
    ├── Transport Extension — 拦截请求自动记录 ActionLog
    └── 事件订阅 — 长驻进程 WebSocket → NDJSON → 文件输出
```

关键约束：
- 编排层通过 subprocess 调用 CLI 命令，解析 JSON 输出
- Transport Extension 自动记录每个飞书 API 调用到 ActionLog
- 事件订阅是唯一长驻 CLI 进程，主进程通过文件监听消费事件

## 核心业务概念

### 数据对象

Project、Member、Task、ConversationState、EventLog、ActionLog、Observation、Decision。完整字段定义见 `docs/prd/02-data-and-event-model.md`。

### 关键状态枚举

- **Project.status**: `creating` → `created` → `initializing_workspace` → `active` / `failed` / `archived`
- **workspace_status**: `pending` → `running` → `succeeded` / `partial_failed` / `failed`
- **Task.status**: `todo` / `in_progress` / `blocked` / `done` / `cancelled`
- **Decision.autonomy_level**: `auto` / `approval` / `forbidden`

### 事件驱动

所有内部事件必须带 `idempotency_key`。核心事件：`project.created`、`project.workspace_initialized`、`task.overdue`、`task.blocked`、`task.stale`、`schedule.daily_standup`、`schedule.weekly_report`。

### AI 模型层级

- `fast`：简单摘要、命令响应
- `smart`：风险分析、周报、站会摘要
- `reasoning`：复杂推理、策略生成

## 里程碑

| 里程碑 | 目标 | 模块 PRD |
|--------|------|----------|
| M0 | 飞书交互链路打通 | `modules/05-platform-and-observability.md` |
| M1 | 项目创建可用 | `modules/01-project-entry-and-onboarding.md` |
| M2 | 飞书工作空间初始化 | `modules/02-feishu-workspace.md` |
| M3 | 项目运行与协作 | `modules/03-project-operations-and-collaboration.md` |
| M4 | AI 能力增强 | `modules/04-ai-analysis-and-decision.md` |

开发时必须按 M0→M4 顺序推进，验收标准见 `docs/prd/03-acceptance-checklist.md`。

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

## cli 子目录

`cli/` 是飞书官方 CLI (lark-cli) 源码。TeamFlow 基于它编译自定义 `teamflow-cli`，注入 Credential 和 Transport 扩展。开发时关注：

- `extension/credential/` — 凭证扩展接口（`credential.Provider`）
- `extension/transport/` — 传输扩展接口（`transport.Provider` + `transport.Interceptor`）
- `shortcuts/` — 200+ 业务命令实现，每个 shortcut 包含 Validate/DryRun/Execute
- `shortcuts/register.go` — 命令注册入口
- `sidecar/protocol.go` — 认证代理协议（TeamFlow 不使用 sidecar，但 Credential Extension 取代其职责）

## hermes-agent 子目录

`hermes-agent/` 是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的参考实现。该目录有自己独立的 `AGENTS.md`。

可参考的架构模式：
- `gateway/platforms/feishu.py` — 飞书平台适配器
- `tools/registry.py` — 工具注册与发现机制

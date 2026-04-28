# TeamFlow 技术架构

## 1. 文档目的

定义 TeamFlow 的技术选型、分层架构和关键集成方式。本文是 PRD 的技术规格补充，与产品需求文档共同构成开发依据。

## 2. 架构总览

TeamFlow 采用 **Python 主进程 + Go CLI 执行层** 的混合架构：

```text
┌──────────────────────────────────────────────────────┐
│  TeamFlow 主进程 (Python)                             │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 接入层    │  │ 业务编排层    │  │ AI 层         │  │
│  │ 事件分发  │  │ 状态机       │  │ LiteLLM       │  │
│  │ 消息路由  │  │ 会话管理     │  │ 提示词管理    │  │
│  │ 指令解析  │  │ 流程编排     │  │ 风险分析      │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ 调度层        │  │ 数据层       │                  │
│  │ APScheduler   │  │ SQLModel     │                  │
│  │ 定时任务      │  │ SQLite       │                  │
│  └──────────────┘  └──────────────┘                  │
│                                                      │
│  执行层 → subprocess 调用 ↓                           │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│  teamflow-cli (Go，基于 lark-cli 编译)                │
│                                                      │
│  ┌─────────────────┐  ┌─────────────────────────┐   │
│  │ Credential 扩展  │  │ Transport 扩展           │   │
│  │ 从 TeamFlow 配置 │  │ 拦截所有 HTTP 请求       │   │
│  │ 读取凭证         │  │ 自动记录结构化日志       │   │
│  └─────────────────┘  │ → 写入 ActionLog         │   │
│                       └─────────────────────────┘   │
│  事件订阅：长驻进程，NDJSON 输出                      │
└──────────────────────────────────────────────────────┘
```

## 3. 技术选型

### 3.1 主进程：Python

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | AI 生态成熟、迭代速度快 |
| 数据库 ORM | SQLModel | 类型安全、Pydantic 原生集成 |
| 数据库 | SQLite（第一阶段） | 零运维、单机足够 |
| 调度 | APScheduler | 轻量、支持 interval/cron |
| AI 调用 | LiteLLM | 统一多模型接口、成本控制 |
| 异步框架 | asyncio | 主进程内异步并发 |

### 3.2 执行层：Go CLI

| 组件 | 选型 | 理由 |
|------|------|------|
| 基础 | lark-cli（飞书官方 CLI） | 200+ 命令覆盖全业务域、经过生产验证 |
| 凭证管理 | Credential Extension | 从 TeamFlow 配置读取，不依赖 CLI 内置认证 |
| 请求追踪 | Transport Extension | 拦截请求自动记录 ActionLog |
| 事件订阅 | `event +subscribe` | WebSocket 长连接、NDJSON 输出、正则路由 |

### 3.3 不选方案及原因

| 方案 | 不选原因 |
|------|----------|
| 纯 Python + 飞书 SDK | SDK 覆盖不全、需逐接口封装、维护成本高 |
| 纯 Go 实现 | AI 生态弱、业务逻辑迭代慢 |
| MCP Server 模式 | 当前阶段不需要通用工具协议、增加部署复杂度 |

## 4. 分层职责

### 4.1 接入层（Python）

职责：
1. 接收 teamflow-cli 事件订阅进程的 NDJSON 输出
2. 解析事件类型和内容
3. 路由到对应的业务处理器
4. 过滤 Bot 自身消息和重复事件

不承载业务逻辑，仅做事件分发。

### 4.2 业务编排层（Python）

职责：
1. 管理会话状态机（项目创建引导）
2. 编排多步业务流程（工作空间初始化）
3. 管理内部事件发布/消费
4. 调用执行层执行具体动作
5. 处理执行结果并决定后续步骤

不直接操作外部系统，通过执行层间接调用。

### 4.3 执行层（Go CLI via subprocess）

职责：
1. 封装所有飞书 API 调用
2. 管理凭证（Credential Extension）
3. 自动记录动作日志（Transport Extension）
4. 事件订阅长驻进程
5. 返回结构化 JSON 结果

主进程通过 subprocess 调用 CLI 命令，解析 JSON 输出。

### 4.4 AI 层（Python）

职责：
1. 模型调用和层级路由（fast/smart/reasoning）
2. 提示词管理
3. 输出格式校验和修复
4. 失败降级

独立于执行层，不直接调用飞书 API。

## 5. teamflow-cli 集成设计

### 5.1 编译和扩展

teamflow-cli 基于 lark-cli 源码编译，通过 Go 的 blank import 机制注入两个扩展：

```go
package main

import (
    _ "github.com/larksuite/cli/extension/credential" // 凭证扩展
    _ "github.com/larksuite/cli/extension/transport"  // 传输扩展
    "github.com/larksuite/cli/internal/cmdutil"
    "github.com/larksuite/cli/cmd"
)

func main() {
    cmd.Execute()
}
```

### 5.2 Credential Extension

实现 `credential.Provider` 接口，从 TeamFlow 配置读取凭证：

```text
TeamFlow 配置 (config.yaml)
  → app_id、app_secret
  → Credential Extension 读取
  → CLI 内部认证流程使用
```

支持 bot 和 user 两种身份模式，CLI 通过 `--as bot` 或 `--as user` 选择身份。

### 5.3 Transport Extension

实现 `transport.Provider` + `transport.Interceptor` 接口：

1. **PreRoundTrip**：拦截每个 HTTP 请求，提取请求信息（method、path、body hash）
2. **PostRoundTrip**：拦截响应，提取结果信息（status、response body 摘要）
3. **结构化输出**：将请求/响应摘要写入 stderr 或指定文件，格式为 ActionLog 兼容的 JSON

Transport Extension 的自动日志能力意味着业务编排层无需手动记录每个飞书动作的 ActionLog，只需解析 CLI 输出中的结构化日志。

### 5.4 CLI 命令映射

TeamFlow 业务动作与 CLI 命令的对应关系：

| 业务动作 | CLI 命令 | 关键参数 |
|----------|----------|----------|
| 发送私聊消息 | `im +messages-send --user-id {open_id} --text {text}` | `--as bot` 或 `--as user` |
| 发送群消息 | `im +messages-send --chat-id {chat_id} --text {text}` | `--as bot` |
| 创建群 | `im +chat-create --name {name} --users {open_ids}` | `--type private/public` |
| 拉人入群 | `im +chat-members-add --chat-id {chat_id} --users {open_ids}` | — |
| 获取群链接 | `im +chat-link --chat-id {chat_id}` | — |
| 创建文档 | `docs +create --title {title} --content {content}` | — |
| 订阅事件 | `event +subscribe --event-types {types}` | `--output-dir`、`--route` |

### 5.5 事件订阅集成

事件订阅是唯一的长驻 CLI 进程：

```text
teamflow-cli event +subscribe \
  --event-types im.message.receive_v1,... \
  --compact \
  --output-dir /tmp/teamflow/events \
  --route '^im\.message=dir:./events/im/' \
  --route '^im\.chat=dir:./events/chat/'
```

主进程通过以下方式消费事件：

1. **文件监听模式**：`--output-dir` + `--route` 将事件写入文件，主进程 watch 目录变化
2. **管道模式**（可选）：CLI 的 stdout NDJSON 直接 pipe 到主进程 stdin

推荐使用文件监听模式，因为支持事件路由分类，且进程重启不丢事件。

## 6. 进程间通信

### 6.1 请求-响应模式（短命令）

```text
Python 主进程
  → subprocess.run(["teamflow-cli", "im", "+messages-send", ...])
  → 解析 stdout JSON 输出
  → 解析 stderr 结构化日志（ActionLog）
  → 返回结果给编排层
```

### 6.2 事件流模式（长驻进程）

```text
teamflow-cli event +subscribe (长驻进程)
  → 事件写入 output-dir 目录
  → Python 主进程 watch 目录
  → 读取 NDJSON 文件
  → 解析并路由到事件处理器
```

### 6.3 配置传递

主进程通过环境变量和配置文件向 CLI 传递配置：

```text
LARKSUITE_CLI_AUTH_PROXY=    # 不使用 sidecar 代理
TEAMFLOW_CONFIG_PATH=        # 指向 TeamFlow 配置文件
TEAMFLOW_APP_ID=             # 飞书应用 App ID
TEAMFLOW_APP_SECRET=         # 飞书应用 App Secret
```

Credential Extension 从 `TEAMFLOW_CONFIG_PATH` 或环境变量读取凭证。

## 7. 目录结构规划

```text
teamflow/
├── docs/prd/                    # 产品需求文档
├── cli/                         # lark-cli 源码（上游）
├── src/
│   ├── teamflow/
│   │   ├── core/                # 核心领域模型（Project, Task, Member...）
│   │   ├── access/              # 接入层（事件解析、消息路由、指令解析）
│   │   ├── orchestration/       # 业务编排层（状态机、流程编排、事件总线）
│   │   ├── execution/           # 执行层（CLI subprocess 封装、结果解析）
│   │   ├── ai/                  # AI 层（模型调用、提示词、降级）
│   │   ├── scheduling/          # 调度层（定时任务）
│   │   ├── storage/             # 数据层（SQLModel 模型、Repository）
│   │   └── config/              # 配置管理
│   ├── teamflow-cli/            # 自定义 CLI（Go）
│   │   ├── main.go              # 入口，注入扩展
│   │   ├── credential_ext/      # Credential Extension 实现
│   │   └── transport_ext/       # Transport Extension 实现
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
├── hermes-agent/                # 参考实现
├── pyproject.toml
├── CLAUDE.md
└── TODO.md
```

## 8. 部署架构

### 8.1 单机部署（第一阶段）

```text
┌──────────────────────────────────┐
│  单机/容器                        │
│                                  │
│  ┌─────────────────────────┐    │
│  │ Python 主进程            │    │
│  │ - 接入层                  │    │
│  │ - 业务编排层              │    │
│  │ - AI 层                  │    │
│  │ - 调度层                  │    │
│  │ - 数据层 (SQLite)        │    │
│  └────────┬────────────────┘    │
│           │ subprocess           │
│  ┌────────▼────────────────┐    │
│  │ teamflow-cli (Go)       │    │
│  │ - 短命令按需调用         │    │
│  │ - 事件订阅长驻进程       │    │
│  └─────────────────────────┘    │
└──────────────────────────────────┘
```

### 8.2 进程管理

1. 主进程负责启动和监控事件订阅子进程
2. 事件订阅进程异常退出时自动重启
3. 短命令通过同步 subprocess.run 调用
4. CLI 二进制文件随主进程一起打包分发

## 9. 关键设计决策

### 9.1 为什么选 subprocess 而非 Go 共享库

1. **隔离性**：CLI 崩溃不影响主进程
2. **复用性**：直接复用 lark-cli 的 200+ 命令，无需重新封装 SDK
3. **可调试性**：CLI 命令可独立运行和调试
4. **版本解耦**：CLI 可独立升级，不影响主进程

### 9.2 为什么选 Python 而非全 Go

1. **AI 生态**：LiteLLM、LangChain、提示词管理都在 Python 生态
2. **迭代速度**：业务逻辑和 AI 提示词需要快速迭代
3. **类型安全**：SQLModel + Pydantic 提供足够的类型保障

### 9.3 为什么 Transport Extension 自动记录 ActionLog

1. **零侵入**：业务编排层无需手动记录每个飞书动作
2. **完整性**：所有飞书 API 调用自动记录，不会遗漏
3. **一致性**：日志格式统一，便于审计和问题定位
4. **性能**：在 CLI 进程内拦截，无额外网络开销

## 10. 性能考量

1. **subprocess 开销**：每次 CLI 调用约 50-100ms 启动时间，对于消息发送场景可接受
2. **事件吞吐**：文件监听模式下，单文件写入 → 主进程读取，延迟在 100ms 以内
3. **并发控制**：主进程通过 asyncio 并发调度多个 CLI 命令，但需控制并发数避免限流
4. **CLI 连接复用**：短命令每次独立进程，无连接池；事件订阅是长连接

## 11. 安全考量

1. **凭证隔离**：App Secret 仅存在于 Credential Extension 和主进程配置中
2. **日志脱敏**：Transport Extension 在记录日志前对 token 和 secret 进行脱敏
3. **进程隔离**：CLI 子进程崩溃不影响主进程
4. **配置文件权限**：配置文件仅主进程用户可读

## 12. 演进方向

第一阶段以 subprocess + 文件监听为主。后续可根据需要演进：

1. **gRPC 模式**：将 CLI 改为长驻 gRPC 服务，减少进程启动开销
2. **MCP Server 模式**：暴露 MCP 协议供外部 Agent 直接调用
3. **分布式部署**：主进程和 CLI 分离部署，通过消息队列通信

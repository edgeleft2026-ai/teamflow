# TeamFlow 技术架构

## 1. 文档目的

定义 TeamFlow 的技术选型、分层架构和关键集成方式。本文是 PRD 的技术规格补充，与产品需求文档共同构成开发依据。

## 2. 架构总览

TeamFlow 采用 **Python 主进程 + lark-cli 执行层** 的混合架构：

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
│  lark-cli (飞书官方 CLI，预编译 Go 二进制)             │
│                                                      │
│  Python 执行层封装：                                   │
│  - 从 config.yaml 读取凭证                            │
│  - 注入环境变量 (LARKSUITE_CLI_APP_ID 等)             │
│  - subprocess 调用 CLI 命令                           │
│  - 捕获 stdout (JSON) + stderr (日志)                 │
│                                                      │
│  事件订阅：长驻进程，NDJSON 输出                       │
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

### 3.2 执行层：lark-cli

| 组件 | 选型 | 理由 |
|------|------|------|
| 基础 | lark-cli（飞书官方 CLI） | 200+ 命令覆盖全业务域、经过生产验证 |
| 凭证注入 | Python 环境变量注入 | 从 config.yaml 读取，通过 LARKSUITE_CLI_APP_ID 等环境变量传递 |
| 日志捕获 | Python stderr 捕获 | 执行层封装自动捕获 CLI 输出 |
| 事件订阅 | `event +subscribe` | WebSocket 长连接、NDJSON 输出、正则路由 |

### 3.3 不选方案及原因

| 方案 | 不选原因 |
|------|----------|
| 纯 Python + 飞书 SDK | SDK 覆盖不全、需逐接口封装、维护成本高 |
| 纯 Go 实现 | AI 生态弱、业务逻辑迭代慢 |
| MCP Server 模式 | 当前阶段不需要通用工具协议、增加部署复杂度 |
| 自定义 Go 二进制（fork lark-cli） | 需要 Go 工具链、维护成本高、后续需要时再引入 |

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

### 4.3 执行层（lark-cli via subprocess）

职责：
1. 封装所有飞书 API 调用
2. 通过环境变量注入凭证
3. 捕获 CLI 输出作为日志
4. 事件订阅长驻进程
5. 返回结构化 JSON 结果

主进程通过 `src/teamflow/execution/cli.py` 封装 subprocess 调用。

### 4.4 AI 层（Python）

职责：
1. 模型调用和层级路由（fast/smart/reasoning）
2. 提示词管理
3. 输出格式校验和修复
4. 失败降级

独立于执行层，不直接调用飞书 API。

## 5. lark-cli 集成设计

### 5.1 执行层封装

Python 执行层（`src/teamflow/execution/cli.py`）封装 lark-cli subprocess 调用：

```text
Python 执行层
  → 从 config.yaml 读取 App ID / App Secret
  → 注入环境变量: LARKSUITE_CLI_APP_ID, LARKSUITE_CLI_APP_SECRET, LARKSUITE_CLI_BRAND
  → subprocess.run(["lark-cli", ...args], env=env, capture_output=True)
  → 解析 stdout JSON (业务结果)
  → 捕获 stderr (CLI 日志)
  → 返回 CLIResult(success, output, error, stderr_log)
```

lark-cli 内置的 env credential provider 自动从环境变量读取凭证，无需自定义扩展。

### 5.2 凭证传递

```text
config.yaml → Python load_config() → FeishuConfig
  → run_cli() 注入环境变量 → lark-cli env provider 读取
  → CLI 内部认证流程使用
```

支持 bot 和 user 两种身份模式，CLI 通过 `--as bot` 或 `--as user` 选择身份。

### 5.3 日志捕获

Python 执行层捕获 lark-cli 的 stderr 输出作为日志：

1. CLI 正常输出：stdout 中的 JSON（解析为业务结果）
2. CLI 错误输出：stderr 中的文本（记录为 stderr_log）
3. 错误信息提取：优先从 JSON 中提取 msg/message 字段，否则取首行文本

### 5.4 CLI 命令映射

TeamFlow 业务动作与 CLI 命令的对应关系：

| 业务动作 | CLI 命令 | 关键参数 |
|----------|----------|----------|
| 发送私聊消息 | `lark-cli im +messages-send --user-id {open_id} --text {text}` | `--as bot` 或 `--as user` |
| 发送群消息 | `lark-cli im +messages-send --chat-id {chat_id} --text {text}` | `--as bot` |
| 创建群 | `lark-cli im +chat-create --name {name} --users {open_ids}` | `--type private/public` |
| 拉人入群 | `lark-cli im +chat-members-add --chat-id {chat_id} --users {open_ids}` | — |
| 获取群链接 | `lark-cli im +chat-link --chat-id {chat_id}` | — |
| 创建文档 | `lark-cli docs +create --title {title} --content {content}` | — |
| 订阅事件 | `lark-cli event +subscribe --event-types {types}` | `--output-dir`、`--route` |

### 5.5 事件订阅集成

事件订阅是唯一的长驻 CLI 进程：

```text
lark-cli event +subscribe \
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
  → run_cli(["im", "+messages-send", ...], feishu_config)
  → subprocess.run(["lark-cli", ...], env={注入凭证})
  → 解析 stdout JSON 输出
  → 捕获 stderr 日志
  → 返回 CLIResult 给编排层
```

### 6.2 事件流模式（长驻进程）

```text
lark-cli event +subscribe (长驻进程，环境变量注入凭证)
  → 事件写入 output-dir 目录
  → Python 主进程 watch 目录
  → 读取 NDJSON 文件
  → 解析并路由到事件处理器
```

### 6.3 配置传递

主进程通过环境变量向 CLI 传递配置：

```text
LARKSUITE_CLI_APP_ID=        # 飞书应用 App ID
LARKSUITE_CLI_APP_SECRET=    # 飞书应用 App Secret
LARKSUITE_CLI_BRAND=         # "feishu" 或 "lark"
```

Python 执行层从 `config.yaml`（路径由 `TEAMFLOW_CONFIG_PATH` 指定）读取凭证，注入上述环境变量。

## 7. 目录结构规划

```text
teamflow/
├── docs/prd/                    # 产品需求文档
├── cli/                         # lark-cli 源码（参考学习，不直接引用）
├── src/
│   ├── teamflow/
│   │   ├── core/                # 核心领域模型（Project, Task, Member...）
│   │   ├── access/              # 接入层（事件解析、消息路由、指令解析）
│   │   ├── orchestration/       # 业务编排层（状态机、流程编排、事件总线）
│   │   ├── execution/           # 执行层（lark-cli subprocess 封装、结果解析）
│   │   ├── ai/                  # AI 层（模型调用、提示词、降级）
│   │   ├── scheduling/          # 调度层（定时任务）
│   │   ├── storage/             # 数据层（SQLModel 模型、Repository）
│   │   └── config/              # 配置管理（YAML 读取、环境变量注入）
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
├── hermes-agent/                # 参考实现（不直接引用）
├── pyproject.toml
├── config.example.yaml
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
│  │ lark-cli (预编译 Go)    │    │
│  │ - 短命令按需调用         │    │
│  │ - 事件订阅长驻进程       │    │
│  └─────────────────────────┘    │
└──────────────────────────────────┘
```

### 8.2 进程管理

1. 主进程负责启动和监控事件订阅子进程
2. 事件订阅进程异常退出时自动重启
3. 短命令通过同步 subprocess.run 调用
4. lark-cli 二进制需要预安装或随主进程一起打包分发

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

### 9.3 为什么用环境变量注入而非自定义 Go 扩展

1. **零编译**：不需要 fork lark-cli 源码和编译自定义二进制
2. **即时可用**：安装 lark-cli 即可使用，无需 Go 工具链
3. **维护简单**：lark-cli 升级时直接替换二进制，无需重新编译
4. **官方支持**：lark-cli 内置 env credential provider，环境变量注入是官方支持的方式

## 10. 性能考量

1. **subprocess 开销**：每次 CLI 调用约 50-100ms 启动时间，对于消息发送场景可接受
2. **事件吞吐**：文件监听模式下，单文件写入 → 主进程读取，延迟在 100ms 以内
3. **并发控制**：主进程通过 asyncio 并发调度多个 CLI 命令，但需控制并发数避免限流
4. **CLI 连接复用**：短命令每次独立进程，无连接池；事件订阅是长连接

## 11. 安全考量

1. **凭证隔离**：App Secret 仅存在于 config.yaml 和进程环境变量中
2. **日志脱敏**：config.yaml 加入 .gitignore，不进入版本控制
3. **进程隔离**：CLI 子进程崩溃不影响主进程
4. **配置文件权限**：config.yaml 仅主进程用户可读

## 12. 演进方向

第一阶段以 subprocess + 环境变量注入为主。后续可根据需要演进：

1. **自定义 Go 二进制**：fork lark-cli 源码，注入 Credential/Transport Extension，实现自动 ActionLog
2. **gRPC 模式**：将 CLI 改为长驻 gRPC 服务，减少进程启动开销
3. **MCP Server 模式**：暴露 MCP 协议供外部 Agent 直接调用
4. **分布式部署**：主进程和 CLI 分离部署，通过消息队列通信

# TeamFlow 技术架构

## 1. 文档目的

定义 TeamFlow 的技术选型、分层架构和关键集成方式。本文是 PRD 的技术规格补充，与产品需求文档共同构成开发依据。

## 2. 架构总览

TeamFlow 采用 **Python 主进程 + 双通道执行层** 的混合架构：确定性动作走 subprocess 直连 lark-cli，复杂编排走 AI Agent + MCP 智能通道。

```text
┌──────────────────────────────────────────────────────────────────┐
│  TeamFlow 主进程 (Python)                                         │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │ 接入层    │  │ 业务编排层    │  │ AI 层                     │  │
│  │ 事件分发  │  │ 状态机       │  │ LiteLLM + Agent Loop      │  │
│  │ 消息路由  │  │ 会话管理     │  │ 提示词管理                │  │
│  │ 指令解析  │  │ 流程编排     │  │ 风险分析                  │  │
│  └──────────┘  └──────┬───────┘  └─────────────┬─────────────┘  │
│                       │                        │                │
│          ┌────────────┴────────────────────────┘                │
│          │  双通道执行调度                                       │
│          │                                                      │
│          │  简单/确定性动作 ──→ subprocess (lark-cli)             │
│          │  复杂/多步编排 ───→ Agent + MCP (lark-openapi-mcp)    │
│          │                                                      │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ 调度层        │  │ 数据层       │                             │
│  │ APScheduler   │  │ SQLModel     │                             │
│  │ 定时任务      │  │ SQLite       │                             │
│  └──────────────┘  └──────────────┘                             │
└──────────────────────────┬───────────────────────┬───────────────┘
                           │                       │
              ┌────────────▼─────────┐ ┌───────────▼───────────────┐
              │ lark-cli             │ │ @larksuiteoapi/lark-mcp   │
              │ (预编译 Go 二进制)    │ │ (官方 MCP Server, stdio)   │
              │                      │ │                           │
              │ · 高频确定性动作      │ │ · Agent 动态发现工具       │
              │ · 事件订阅长驻进程    │ │ · 全量 OpenAPI 覆盖       │
              │ · 消息发送           │ │ · 多步编排与错误恢复      │
              └────────────┬─────────┘ └────────────┬──────────────┘
                           └──────────┬─────────────┘
                                      ▼
                               飞书 OpenAPI
```

## 3. 技术选型

### 3.1 主进程：Python

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | AI 生态成熟、迭代速度快 |
| 数据库 ORM | SQLModel | 类型安全、Pydantic 原生集成 |
| 数据库 | SQLite（第一阶段） | 零运维、单机足够 |
| 调度 | APScheduler | 轻量、支持 interval/cron |
| AI 调用 | LiteLLM | 统一多模型接口、原生 tool-use 支持 |
| MCP 客户端 | `mcp` (Python SDK) | 官方 MCP 协议实现，支持 stdio client |
| 异步框架 | asyncio | 主进程内异步并发 |

### 3.2 Agent 层：LiteLLM + MCP

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent 框架 | LiteLLM + 自建 tool-use 循环 | 模型无关、轻量、TeamFlow 场景足够简单 |
| MCP Server | `@larksuiteoapi/lark-mcp`（飞书官方） | 全量 OpenAPI、官方维护、Beta |
| MCP Client | Python `mcp` SDK（stdio transport） | 官方协议实现、Agent 动态发现工具 |
| 凭证传递 | 启动参数 `-a <app_id> -s <app_secret>` | MCP Server 内部管理 token 生命周期 |

### 3.3 执行层：双通道

| 通道 | 技术 | 适用场景 |
|------|------|----------|
| 确定性通道 | lark-cli subprocess | 发消息、拉人入群、事件订阅等高频确定性动作 |
| 智能通道 | Agent + lark-openapi-mcp | 创建工作空间、生成报告、风险分析等多步编排 |

### 3.4 不选方案及原因

| 方案 | 不选原因 |
|------|----------|
| 纯 Python + 飞书 SDK | SDK 覆盖不全、需逐接口封装、维护成本高 |
| 纯 Go 实现 | AI 生态弱、业务逻辑迭代慢 |
| LangChain / LangGraph | 抽象层过重、TeamFlow 的 Agent 循环只需 20 行 |
| Claude Agent SDK | 供应商锁定、TeamFlow 需要灵活切模型 |
| 单通道全走 Agent | 高频确定性动作（发消息）走 Agent 有不必要的延迟和 token 开销 |
| 自定义 Go 二进制（fork lark-cli） | 需要 Go 工具链、维护成本高、后续需要时再引入 |
| 远程 MCP 服务 | 目前仅支持云文档、Beta 阶段，待成熟后可切换 |

## 4. 分层职责

### 4.1 接入层（Python）

职责：
1. 接收 lark-cli 事件订阅进程的 NDJSON 输出
2. 解析事件类型和内容
3. 路由到对应的业务处理器
4. 过滤 Bot 自身消息和重复事件

不承载业务逻辑，仅做事件分发。

### 4.2 业务编排层（Python）

职责：
1. 管理会话状态机（项目创建引导）
2. 编排多步业务流程（工作空间初始化）
3. 管理内部事件发布/消费
4. **根据动作复杂度选择执行通道**：
   - 简单确定性动作 → 直接调用确定性通道
   - 复杂多步编排 → 委托 Agent 智能通道
5. 处理执行结果并决定后续步骤

不直接操作外部系统，通过执行层间接调用。

### 4.3 执行层（双通道）

**确定性通道**（`execution/cli.py`，已实现）：
1. subprocess 调用 lark-cli 命令
2. 环境变量注入凭证
3. 捕获 CLI 输出作为日志
4. 返回结构化 `CLIResult`

**智能通道**（`ai/agent.py`，待实现）：
1. 构建任务描述和上下文
2. 调用 Agent executor 执行
3. Agent 通过 MCP 动态发现和调用飞书工具
4. 返回结构化 `AgentResult`

### 4.4 AI 层 / Agent（Python）

职责：
1. Agent executor：LiteLLM tool-use 循环
2. MCP 客户端管理：连接生命周期、工具发现
3. 模型路由：fast / smart / reasoning 三级
4. 提示词管理：系统角色、任务模板
5. 输出格式校验和失败降级

### 4.5 调度层（Python）

职责：
1. 定时任务管理（cron / interval）
2. 触发定时扫描（逾期、停滞、报告生成）
3. 定时任务可以选择执行通道

### 4.6 数据层（Python）

职责：
1. 领域模型定义（SQLModel）
2. Repository 封装
3. 数据库迁移

## 5. Agent 架构

### 5.1 核心组件

```text
┌─────────────────────────────────────────────┐
│  Agent Executor (ai/agent.py)               │
│                                             │
│  输入：task_description + context           │
│                                             │
│  ┌─────────────┐    ┌──────────────────┐   │
│  │ LiteLLM     │    │ MCP Client       │   │
│  │ tool-use    │←──→│ (stdio transport) │   │
│  │ 循环        │    │                  │   │
│  └─────────────┘    └────────┬─────────┘   │
│                              │              │
│  输出：AgentResult           │              │
│  (success, actions, data)    │              │
└──────────────────────────────┼──────────────┘
                               │ stdio
                    ┌──────────▼──────────────┐
                    │ @larksuiteoapi/lark-mcp  │
                    │ MCP Server 子进程        │
                    └──────────┬──────────────┘
                               │ HTTP
                    ┌──────────▼──────────────┐
                    │ 飞书 OpenAPI             │
                    └─────────────────────────┘
```

### 5.2 Agent 执行循环

```python
async def execute_agent_task(task: AgentTask) -> AgentResult:
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": task.description}]

    while True:
        response = await litellm.acompletion(
            model=route_model(task.complexity),
            messages=messages,
            tools=mcp_tools,
        )

        if has_tool_calls(response):
            for tool_call in extract_tool_calls(response):
                result = await mcp_client.call_tool(
                    tool_call.name, tool_call.arguments
                )
                messages.append(tool_result_message(tool_call, result))
        else:
            return AgentResult(
                success=True,
                summary=response.content,
                actions=extract_actions(messages),
            )
```

### 5.3 MCP Server 管理

TeamFlow 启动时管理两个长驻子进程：

| 子进程 | 启动命令 | 用途 |
|--------|----------|------|
| lark-cli event +subscribe | 事件订阅 | 接入飞书实时事件 |
| @larksuiteoapi/lark-mcp | Agent 工具服务 | Agent 调用飞书 API |

MCP Server 启动命令：

```bash
npx -y @larksuiteoapi/lark-mcp mcp \
  -a <app_id> \
  -s <app_secret> \
  -t "im.v1.chat.create,im.v1.chat.members.create,im.v1.message.create,\
preset.docx.default,preset.calendar.default,preset.task.default"
```

工具集按里程碑渐进启用：

| 里程碑 | 启用的工具集 |
|--------|-------------|
| M2 | `im.v1.*`, `docx.v1.*` |
| M3 | + `calendar.v1.*`, `task.v1.*`, `sheet.v1.*` |
| M4 | + `search.*`, `mail.v1.*`, `approval.v4.*` |

### 5.4 Agent 任务接口

编排层通过统一接口委托 Agent：

```python
@dataclass
class AgentTask:
    description: str          # 自然语言任务描述
    context: dict             # 项目 ID、用户信息等上下文
    complexity: str           # "fast" / "smart" / "reasoning"
    max_iterations: int = 10  # 防止无限循环
    allowed_tools: list[str] | None = None  # 工具白名单（可选）

@dataclass
class AgentResult:
    success: bool
    summary: str              # Agent 对执行结果的描述
    actions: list[dict]       # 已执行的动作列表（用于审计）
    data: dict | None = None  # 结构化返回数据
    error: str | None = None
```

## 6. 双通道执行调度

### 6.1 确定性通道（subprocess）

**适用条件**：动作参数完全确定、不需要 AI 判断、高频调用。

| 动作 | 命令 | 通道 |
|------|------|------|
| 发送文本消息 | `lark-cli im +messages-send` | 确定性 |
| 发送卡片消息 | `lark-cli im +messages-send --msg-type interactive` | 确定性 |
| 拉人入群 | `lark-cli im +chat-members-add` | 确定性 |
| 获取群链接 | `lark-cli im +chat-link` | 确定性 |
| 事件订阅 | `lark-cli event +subscribe` | 确定性 |

### 6.2 智能通道（Agent + MCP）

**适用条件**：多步编排、需要根据中间结果判断、涉及 AI 生成内容。

| 动作 | 通道 | 原因 |
|------|------|------|
| 初始化工作空间（创建群+文档+欢迎语） | 智能 | 多步编排、部分失败处理 |
| 生成每日站会摘要 | 智能 | 需要聚合数据+AI 生成内容 |
| 生成周报 | 智能 | 需要分析+AI 写作 |
| 风险分析 | 智能 | 需要 AI 推理 |
| 自然语言查询 | 智能 | 需要理解意图+查数据+组织回答 |

### 6.3 通道选择原则

```
编排层收到业务动作
  ├─ 参数完全确定 且 单步调用？
  │    → 确定性通道（subprocess）
  │
  ├─ 涉及多步编排 或 需要 AI 判断？
  │    → 智能通道（Agent）
  │
  └─ 不确定？
       → 默认确定性通道，降级安全
```

## 7. lark-cli 集成（确定性通道）

### 7.1 执行层封装

Python 执行层（`execution/cli.py`）封装 lark-cli subprocess 调用：

```text
Python 执行层
  → 从 config.yaml 读取 App ID / App Secret
  → 自动交换 tenant_access_token 并注入环境变量
  → subprocess.run(["lark-cli", ...args], env=env, capture_output=True)
  → 解析 stdout JSON (业务结果)
  → 捕获 stderr (CLI 日志)
  → 返回 CLIResult(success, output, error, stderr_log)
```

### 7.2 凭证传递

```text
config.yaml → Python load_config() → FeishuConfig
  → run_cli() 注入环境变量 → lark-cli env provider 读取
  → CLI 内部认证流程使用
```

支持 bot 和 user 两种身份模式，CLI 通过 `--as bot` 或 `--as user` 选择身份。

### 7.3 日志捕获

1. CLI 正常输出：stdout 中的 JSON（解析为业务结果）
2. CLI 错误输出：stderr 中的文本（记录为 stderr_log）
3. 错误信息提取：优先从 JSON 中提取 msg/message 字段，否则取首行文本

### 7.4 CLI 命令映射

确定性通道的业务动作与 CLI 命令对应关系：

| 业务动作 | CLI 命令 | 关键参数 |
|----------|----------|----------|
| 发送私聊消息 | `lark-cli im +messages-send --user-id {open_id} --text {text}` | `--as bot` 或 `--as user` |
| 发送群消息 | `lark-cli im +messages-send --chat-id {chat_id} --text {text}` | `--as bot` |
| 发送卡片消息 | `lark-cli im +messages-send --chat-id {chat_id} --msg-type interactive --content {json}` | `--as bot` |
| 拉人入群 | `lark-cli im +chat-members-add --chat-id {chat_id} --users {open_ids}` | — |
| 获取群链接 | `lark-cli im +chat-link --chat-id {chat_id}` | — |
| 订阅事件 | `lark-cli event +subscribe --event-types {types}` | `--output-dir`、`--route` |

### 7.5 事件订阅集成

事件订阅是 lark-cli 的长驻进程（不经过 MCP）：

```text
lark-cli event +subscribe \
  --event-types im.message.receive_v1,... \
  --compact \
  --output-dir /tmp/teamflow/events \
  --route '^im\.message=dir:./events/im/' \
  --route '^im\.chat=dir:./events/chat/'
```

主进程通过文件监听消费事件，支持事件路由分类，进程重启不丢事件。

## 8. 进程间通信

### 8.1 确定性通道（短命令）

```text
Python 主进程
  → run_cli(["im", "+messages-send", ...], feishu_config)
  → subprocess.run(["lark-cli", ...], env={注入凭证})
  → 解析 stdout JSON 输出
  → 捕获 stderr 日志
  → 返回 CLIResult 给编排层
```

### 8.2 智能通道（Agent → MCP）

```text
Python 主进程 (编排层)
  → 构建 AgentTask(description, context, complexity)
  → Agent Executor
    → LiteLLM completion(tools=mcp_tools)
    → tool_calls → MCP Client.call_tool(name, args)
      → stdio → @larksuiteoapi/lark-mcp → 飞书 API
      → 返回 tool result
    → 循环直到 Agent 完成
  → 返回 AgentResult 给编排层
```

### 8.3 事件流模式（长驻进程）

```text
lark-cli event +subscribe (长驻进程，环境变量注入凭证)
  → 事件写入 output-dir 目录
  → Python 主进程 watch 目录
  → 读取 NDJSON 文件
  → 解析并路由到事件处理器
```

### 8.4 MCP Server 进程管理

```text
主进程启动
  → 启动 lark-cli event +subscribe (事件订阅子进程)
  → 启动 npx @larksuiteoapi/lark-mcp mcp ... (MCP Server 子进程)
  → MCP Client (Python mcp SDK) 连接到 MCP Server (stdio)
  → tools/list 发现可用工具
  → Agent Executor 就绪
```

## 9. 目录结构

```text
teamflow/
├── docs/prd/                    # 产品需求文档
├── cli/                         # lark-cli 源码（参考学习，不直接引用）
├── src/
│   ├── teamflow/
│   │   ├── core/                # 核心领域模型（Project, Task, Member...）
│   │   ├── access/              # 接入层（事件解析、消息路由、指令解析）
│   │   ├── orchestration/       # 业务编排层（状态机、流程编排、双通道调度）
│   │   ├── execution/           # 执行层
│   │   │   ├── cli.py           # 确定性通道：lark-cli subprocess 封装
│   │   │   └── messages.py      # 消息发送快捷函数
│   │   ├── ai/                  # AI 层
│   │   │   ├── agent.py         # Agent executor：LiteLLM tool-use 循环
│   │   │   ├── mcp.py           # MCP 客户端：连接管理、工具发现
│   │   │   ├── prompts.py       # 提示词管理
│   │   │   └── models.py        # 模型路由（fast/smart/reasoning）与降级
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

## 10. 部署架构

### 10.1 单机部署（第一阶段）

```text
┌──────────────────────────────────────────────────┐
│  单机/容器                                        │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │ Python 主进程                            │    │
│  │ - 接入层                                  │    │
│  │ - 业务编排层（双通道调度）                 │    │
│  │ - AI 层（Agent Executor）                │    │
│  │ - 调度层                                  │    │
│  │ - 数据层 (SQLite)                        │    │
│  └───────┬────────────────────┬─────────────┘    │
│          │ subprocess         │ stdio             │
│  ┌───────▼────────┐ ┌────────▼─────────────┐    │
│  │ lark-cli       │ │ @larksuiteoapi/      │    │
│  │ (预编译 Go)    │ │   lark-mcp (Node.js) │    │
│  │ · 短命令调用   │ │ · MCP Server         │    │
│  │ · 事件订阅     │ │ · Agent 工具服务      │    │
│  └────────────────┘ └──────────────────────┘    │
└──────────────────────────────────────────────────┘
```

### 10.2 进程管理

1. 主进程负责启动和监控三个子进程：
   - lark-cli 事件订阅进程
   - lark-openapi-mcp MCP Server 进程
   - （可选）健康检查 HTTP 服务
2. 所有子进程异常退出时自动重启
3. 短命令通过同步 subprocess.run 调用
4. lark-cli 二进制预安装，lark-openapi-mcp 通过 npx 自动拉取

### 10.3 运行时依赖

| 依赖 | 安装方式 | 用途 |
|------|----------|------|
| Node.js (LTS) | 系统安装 | 运行 lark-openapi-mcp |
| lark-cli | `npm install -g @larksuite/cli` | 确定性通道 + 事件订阅 |
| @larksuiteoapi/lark-mcp | `npx` 自动拉取 | Agent 智能通道 |
| Python 3.12+ | 系统安装 | 主进程 |

## 11. 关键设计决策

### 11.1 为什么选双通道而非全走 Agent

1. **性能**：发消息是高频操作，subprocess 50-100ms；走 Agent 需经 LiteLLM + MCP，延迟高 1-2 个数量级
2. **成本**：每次 Agent 调用消耗 LLM token，发消息不需要 AI 判断
3. **确定性**：简单动作参数完全确定，不需要 AI 决策，避免幻觉风险
4. **可靠性**：确定性通道不依赖 LLM 服务可用性

### 11.2 为什么选 LiteLLM 自建循环而非 Agent 框架

1. **轻量**：TeamFlow 的 Agent 循环本质是 observe → think → act → observe，20 行代码
2. **灵活**：不绑定任何模型供应商，LiteLLM 支持 100+ 模型
3. **透明**：没有隐藏抽象，tool-use 循环完全可控可调试
4. **已选型**：LiteLLM 本身就在技术栈中，不引入新依赖

### 11.3 为什么选 lark-openapi-mcp 而非 lark-cli skills

1. **标准化**：MCP 是标准协议，任何 Agent 都能对接；skills 是 Claude Code 专有格式
2. **动态发现**：Agent 通过 `tools/list` 自动发现可用工具，不需要硬编码
3. **官方维护**：飞书官方 MCP Server，覆盖全量 OpenAPI
4. **独立于 AI 工具**：不依赖 Claude Code / Cursor / Trae 等特定 AI 工具

### 11.4 为什么选 subprocess 而非 Go 共享库

1. **隔离性**：CLI 崩溃不影响主进程
2. **复用性**：直接复用 lark-cli 的 200+ 命令
3. **可调试性**：CLI 命令可独立运行和调试
4. **版本解耦**：CLI 可独立升级

### 11.5 为什么选 Python 而非全 Go

1. **AI 生态**：LiteLLM、MCP SDK、提示词管理都在 Python 生态
2. **迭代速度**：业务逻辑和 AI 提示词需要快速迭代
3. **类型安全**：SQLModel + Pydantic 提供足够的类型保障

### 11.6 为什么用环境变量注入而非自定义 Go 扩展

1. **零编译**：不需要 fork lark-cli 源码和编译自定义二进制
2. **即时可用**：安装 lark-cli 即可使用，无需 Go 工具链
3. **维护简单**：lark-cli 升级时直接替换二进制

## 12. 性能考量

1. **确定性通道开销**：每次 CLI 调用约 50-100ms 启动时间，适合消息发送
2. **智能通道开销**：Agent 单次任务 2-10 秒（取决于 LLM 响应和工具调用轮数），适合低频复杂任务
3. **MCP Server 通信**：stdio 传输，本地进程间通信延迟 < 1ms
4. **事件吞吐**：文件监听模式下延迟在 100ms 以内
5. **并发控制**：确定性通道通过 asyncio 并发调度；智能通道控制并发 Agent 数避免 LLM 限流
6. **工具调用预算**：Agent 设置 `max_iterations`（默认 10），防止无限循环

## 13. 安全考量

1. **凭证隔离**：App Secret 仅存在于 config.yaml 和进程环境变量中
2. **日志脱敏**：config.yaml 加入 .gitignore；Agent 审计日志不含完整敏感输入
3. **进程隔离**：CLI / MCP Server 子进程崩溃不影响主进程
4. **Agent 权限控制**：通过 MCP Server `-t` 参数限制可用工具；`allowed_tools` 白名单进一步约束
5. **自治级别**：高风险动作（删除、移除成员）不加入 Agent 工具集，走确定性通道并需人工确认
6. **配置文件权限**：config.yaml 仅主进程用户可读

## 14. 演进方向

第一阶段以双通道架构为主。后续可根据需要演进：

1. **远程 MCP 服务**：飞书远程 MCP 成熟后，替换本地 MCP Server 子进程，去掉 Node.js 依赖
2. **自定义 Go 二进制**：需要深度定制凭证/监控时，fork lark-cli 编译增强版
3. **gRPC 模式**：将 CLI 改为长驻 gRPC 服务，减少进程启动开销
4. **流式 Agent**：Agent 执行过程中实时推送进度到飞书（卡片更新）
5. **分布式部署**：主进程和执行层分离部署，通过消息队列通信

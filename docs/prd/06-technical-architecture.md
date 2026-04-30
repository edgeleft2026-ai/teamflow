# TeamFlow 技术架构

## 1. 文档目的

定义 TeamFlow 的技术选型、分层架构和关键集成方式。本文是 PRD 的技术规格补充，与产品需求文档共同构成开发依据。

## 2. 架构总览

TeamFlow 采用 **Python 主进程 + 双通道执行层** 的混合架构：确定性动作走 subprocess 直连 lark-cli 或 lark-oapi SDK，复杂编排走 AI Agent + ToolProvider 智能通道。

```text
┌──────────────────────────────────────────────────────────────────┐
│  TeamFlow 主进程 (Python)                                         │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │ 接入层    │  │ 业务编排层    │  │ AI 层                     │  │
│  │ 事件分发  │  │ 状态机       │  │ LiteLLM + Agent Loop      │  │
│  │ 消息路由  │  │ 会话管理     │  │ ToolProvider + Skills     │  │
│  │ 指令解析  │  │ 流程编排     │  │ Transport + ModelRegistry │  │
│  │ 卡片回调  │  │ 卡片模板     │  │ 风险分析                  │  │
│  └──────────┘  └──────┬───────┘  └─────────────┬─────────────┘  │
│                       │                        │                │
│          ┌────────────┴────────────────────────┘                │
│          │  双通道执行调度                                       │
│          │                                                      │
│          │  简单/确定性动作 ──→ lark-oapi SDK / lark-cli          │
│          │  复杂/多步编排 ───→ Agent + ToolProvider (lark-oapi)   │
│          │                                                      │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ 调度层        │  │ 数据层       │                             │
│  │ APScheduler   │  │ SQLModel     │                             │
│  │ 定时任务      │  │ SQLite       │                             │
│  └──────────────┘  └──────────────┘                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────▼─────────┐
              │ lark-cli             │
              │ (预编译 Go 二进制)    │
              │                      │
              │ · 事件订阅长驻进程    │
              │ · 通用 CLI 透传工具   │
              └────────────┬─────────┘
                           │
              ┌────────────▼─────────┐
              │ lark-oapi SDK        │
              │ (Python 原生)         │
              │                      │
              │ · 确定性通道 API 调用  │
              │ · Agent 工具函数      │
              │ · 卡片消息发送/更新   │
              │ · WebSocket 事件回调  │
              └────────────┬─────────┘
                           │
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
| 飞书 SDK | lark-oapi | Python 原生、官方维护、全量 OpenAPI 覆盖 |
| 异步框架 | asyncio | 主进程内异步并发 |

### 3.2 Agent 层：LiteLLM + ToolProvider

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent 框架 | LiteLLM + 自建 tool-use 循环 | 模型无关、轻量、TeamFlow 场景足够简单 |
| 工具系统 | ToolProvider（Python 原生） | 零外部进程依赖、lark-oapi SDK 直连飞书 API |
| Transport | ChatCompletionsTransport + 扩展点 | 多 provider 响应归一化、支持 reasoning 模型 |
| Model Registry | models.dev 元数据 + 本地缓存 | provider 别名、模型能力查询、LiteLLM 集成映射 |
| Skills | SKILL.md 文件驱动自动发现 | 插件式注册、触发器匹配、上下文变量插值 |
| 凭证传递 | lark-oapi Client 内部管理 | SDK 内部管理 token 生命周期 |

> **设计演进**：最初采用 MCP 协议（`@larksuiteoapi/lark-mcp` MCP Server + Python `mcp` SDK），因飞书 MCP Server v0.5.1 协议不兼容（`tools/list` 返回 Method not found），改为 **ToolProvider**（Python 原生，`lark-oapi` SDK 直连飞书 API，零外部进程依赖）。MCP 方案待飞书官方更新后可平滑切换回。

### 3.3 执行层：双通道

| 通道 | 技术 | 适用场景 |
|------|------|----------|
| 确定性通道 | lark-oapi SDK / lark-cli subprocess | 发消息、拉人入群、事件订阅等高频确定性动作 |
| 智能通道 | Agent + ToolProvider (lark-oapi SDK) | 创建工作空间、生成报告、风险分析等多步编排 |

### 3.4 不选方案及原因

| 方案 | 不选原因 |
|------|----------|
| 纯 lark-cli 全走 subprocess | SDK 覆盖不全、卡片消息更新等需要 SDK patch 能力 |
| 纯 Go 实现 | AI 生态弱、业务逻辑迭代慢 |
| LangChain / LangGraph | 抽象层过重、TeamFlow 的 Agent 循环只需 20 行 |
| Claude Agent SDK | 供应商锁定、TeamFlow 需要灵活切模型 |
| 单通道全走 Agent | 高频确定性动作（发消息）走 Agent 有不必要的延迟和 token 开销 |
| 自定义 Go 二进制（fork lark-cli） | 需要 Go 工具链、维护成本高、后续需要时再引入 |
| MCP 协议（当前） | 飞书 MCP Server v0.5.1 协议不兼容，待官方修复后可切换回 |

## 4. 分层职责

### 4.1 接入层（Python）

职责：
1. 接收 lark-cli 事件订阅进程的 NDJSON 输出（`access/watcher.py`）
2. 接收 WebSocket 卡片交互回调（`access/callback.py`）
3. 解析事件类型和内容（`access/parser.py`）
4. 路由到对应的业务处理器（`access/dispatcher.py`）
5. 过滤 Bot 自身消息和重复事件

不承载业务逻辑，仅做事件分发。

### 4.2 业务编排层（Python）

职责：
1. 管理会话状态机（项目创建引导）
2. 编排多步业务流程（工作空间初始化）
3. 管理内部事件发布/消费（EventBus）
4. **根据动作复杂度选择执行通道**：
   - 简单确定性动作 → 直接调用确定性通道
   - 复杂多步编排 → 委托 Agent 智能通道
5. 处理执行结果并决定后续步骤
6. 卡片模板管理与进度追踪（`orchestration/card_templates.py`）

不直接操作外部系统，通过执行层间接调用。

### 4.3 执行层（双通道）

**确定性通道**（`execution/cli.py` + `execution/messages.py`，已实现）：
1. subprocess 调用 lark-cli 命令
2. lark-oapi SDK 直连调用（消息发送、卡片更新）
3. 环境变量注入凭证
4. 捕获 CLI 输出作为日志
5. 返回结构化 `CLIResult`

**智能通道**（`ai/agent.py`，已实现）：
1. 构建任务描述和上下文
2. 调用 Agent executor 执行
3. Agent 通过 ToolProvider 调用飞书 API 工具
4. 返回结构化 `AgentResult`

### 4.4 AI 层 / Agent（Python）

职责：
1. Agent executor：LiteLLM tool-use 循环
2. ToolProvider 管理：工具注册、调用、日志
3. Transport 层：多 provider 响应归一化
4. Model Registry：provider 定义、别名、模型能力查询
5. Skills 系统：SKILL.md 自动发现、触发器匹配、上下文插值
6. 模型路由：fast / smart / reasoning 三级
7. 提示词管理：系统角色、任务模板
8. 输出格式校验和失败降级

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
┌──────────────────────────────────────────────────────────┐
│  Agent Executor (ai/agent.py)                            │
│                                                          │
│  输入：AgentTask(description, context, complexity, ...)  │
│                                                          │
│  ┌─────────────┐    ┌────────────────────────────────┐  │
│  │ LiteLLM     │    │ ToolProvider (ai/tools/)        │  │
│  │ tool-use    │←──→│ · Python 异步函数注册           │  │
│  │ 循环        │    │ · lark-oapi SDK 直连飞书 API    │  │
│  │             │    │ · lark_cli.run 通用透传         │  │
│  └──────┬──────┘    └────────────┬───────────────────┘  │
│         │                        │                       │
│  ┌──────┴──────┐                 │                       │
│  │ Transport   │                 │                       │
│  │ (归一化层)  │                 │                       │
│  └─────────────┘                 │                       │
│                                  │                       │
│  ┌──────────────┐                │                       │
│  │ Model        │                │                       │
│  │ Registry     │                │                       │
│  └──────────────┘                │                       │
│                                  │                       │
│  输出：AgentResult               │                       │
│  (success, summary, actions)     │                       │
└──────────────────────────────────┼───────────────────────┘
                                   │
                        ┌──────────▼──────────────┐
                        │ lark-oapi SDK           │
                        │ (Python 原生, 零子进程)  │
                        └──────────┬──────────────┘
                                   │ HTTP
                        ┌──────────▼──────────────┐
                        │ 飞书 OpenAPI             │
                        └─────────────────────────┘
```

### 5.2 Agent 执行循环

```python
async def execute(self, task: AgentTask) -> AgentResult:
    tools = _mcp_tools_to_litellm(self._mcp.tools)
    if task.allowed_tools:
        tools = [t for t in tools if t["function"]["name"] in task.allowed_tools]

    model = _resolve_model(task.complexity, self._model_overrides)
    provider_name, model_name = _parse_provider_n_model(model)
    api_mode = detect_api_mode(provider_name, model_name)
    transport = get_transport(api_mode)

    messages = [
        {"role": "system", "content": _build_system_prompt(task)},
        {"role": "user", "content": _format_user_message(task)},
    ]

    for _ in range(self._max_iterations):
        response = await litellm.acompletion(model=model, messages=messages, tools=tools, ...)
        if has_tool_calls(response):
            for tool_call in extract_tool_calls(response):
                result = await self._mcp.call_tool(tool_call.name, tool_call.arguments)
                messages.append(tool_result_message(tool_call, result))
        else:
            return AgentResult(success=True, summary=response.content, actions=...)

    return AgentResult(success=False, error="Max iterations reached")
```

### 5.3 ToolProvider 工具系统

ToolProvider 是 Python 原生的工具注册和调用系统，替代 MCP 协议：

```text
ToolProvider (ai/tools/__init__.py)
  ├── ToolDef: name + description + parameters JSON Schema + handler 函数
  ├── register(tool_def): 注册工具
  ├── call_tool(name, args): 调用工具 handler
  └── to_litellm_tools(): 转换为 LiteLLM function calling 格式

Feishu Tools (ai/tools/feishu.py)
  ├── CHAT_TOOLS: im.v1.chat.create / members.create / get / link
  ├── MESSAGE_TOOLS: im.v1.message.create (text + interactive)
  ├── DOCX_TOOLS: docx.v1.document.create
  ├── DRIVE_TOOLS: drive.v1.permission.add_collaborator / transfer_owner
  ├── BOT_TOOLS: im.v1.bot.info
  └── CLI_TOOLS: lark_cli.run (通用 CLI 透传)
```

工具集按里程碑渐进启用：

| 里程碑 | 启用的工具集 |
|--------|-------------|
| M2 | `im.v1.*`, `docx.v1.*`, `drive.v1.permission.*`, `im.v1.bot.info` |
| M3 | + `lark_cli.run`（透传 calendar/task/sheet 等 API） |
| M4 | + 自定义工具（审批、邮件等） |

### 5.4 Transport 层

Transport 层归一化不同 LLM provider 的响应格式，解决模型间差异：

```text
ProviderTransport (ai/transports/base.py)
  ├── convert_messages(messages) → provider 格式
  ├── convert_tools(tools) → provider 格式
  ├── build_kwargs(...) → provider 请求参数
  └── normalize_response(raw) → NormalizedResponse

ChatCompletionsTransport (ai/transports/chat_completions.py)
  └── OpenAI 兼容格式（默认，覆盖 OpenRouter/DeepSeek/Qwen/Ollama/Groq 等）

NormalizedResponse
  ├── content: str | None
  ├── tool_calls: list[ToolCall]
  ├── usage: Usage
  └── finish_reason: str
```

### 5.5 Model Registry

Model Registry 管理 provider 定义、别名映射和模型能力查询：

```text
ModelRegistry (ai/model_registry.py)
  ├── ProviderEntry: slug / label / auth_type / env_vars / api_mode / base_url
  ├── ModelInfo: tool_call / reasoning / vision / context_window / cost
  ├── PROVIDER_ALIASES: glm→zai / github→copilot 等 30+ 别名
  ├── LITELLM_PROVIDER_MAP / LITELLM_ENV_MAP / LITELLM_BASE_URL_OVERRIDES
  ├── get_model_capabilities(provider, model) → ModelInfo
  ├── supports_reasoning(provider, model) → bool
  └── detect_api_mode(provider, model) → str
```

### 5.6 Skills 系统

Skills 系统支持 SKILL.md 文件驱动的自动发现和触发器匹配：

```text
SkillRegistry (ai/skills/__init__.py)
  ├── Skill: name / triggers / prompt / allowed_tools / complexity / context_vars
  ├── register(skill): 注册 skill
  ├── match(text): 按触发器匹配 skill
  ├── build_task(text, context): 自动匹配 + 构建 AgentTask
  └── discover_from_dir(path): 扫描 SKILL.md 文件自动注册

内置 lark-* Skills (17 个)
  ├── lark-approval / lark-attendance / lark-base / lark-calendar
  ├── lark-contact / lark-doc / lark-drive / lark-event
  ├── lark-im / lark-mail / lark-minutes / lark-okr
  ├── lark-openapi-explorer / lark-sheets / lark-skill-maker
  ├── lark-slides / lark-task
  └── 每个 skill 定义触发词、提示词、允许工具和复杂度
```

### 5.7 Agent 任务接口

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

### 6.1 确定性通道（lark-oapi SDK / subprocess）

**适用条件**：动作参数完全确定、不需要 AI 判断、高频调用。

| 动作 | 技术 | 通道 |
|------|------|------|
| 发送文本消息 | lark-oapi SDK | 确定性 |
| 发送卡片消息 | lark-oapi SDK | 确定性 |
| 更新卡片消息 | lark-oapi SDK patch | 确定性 |
| 拉人入群 | lark-oapi SDK | 确定性 |
| 获取群链接 | lark-oapi SDK | 确定性 |
| 事件订阅 | lark-cli subprocess | 确定性 |
| 通用 CLI 命令 | lark-cli subprocess | 确定性 |

### 6.2 智能通道（Agent + ToolProvider）

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
  │    → 确定性通道（lark-oapi SDK / subprocess）
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

### 7.4 lark-oapi SDK 集成

确定性通道同时使用 lark-oapi SDK 直连飞书 API（`execution/messages.py`）：

```text
Python 执行层
  → 从 config.yaml 读取 App ID / App Secret
  → 初始化 lark-oapi Client
  → 直接调用 SDK 方法（发送消息、更新卡片等）
  → 无子进程开销，延迟更低
```

SDK 覆盖的确定性通道动作：

| 业务动作 | SDK 方法 |
|----------|----------|
| 发送文本消息 | `client.im.v1.message.create()` |
| 发送卡片消息 | `client.im.v1.message.create(msg_type="interactive")` |
| 更新卡片消息 | `client.im.v1.message.patch()` |
| 发送异步消息 | `asyncio.to_thread(client.im.v1.message.create, ...)` |

### 7.5 事件订阅集成

事件订阅是 lark-cli 的长驻进程：

```text
lark-cli event +subscribe \
  --event-types im.message.receive_v1,... \
  --compact \
  --output-dir /tmp/teamflow/events \
  --route '^im\.message=dir:./events/im/' \
  --route '^im\.chat=dir:./events/chat/'
```

主进程通过文件监听消费事件，支持事件路由分类，进程重启不丢事件。

### 7.6 卡片交互回调

卡片交互事件通过 lark-oapi WebSocket 长连接接收（`access/callback.py`）：

```text
lark-oapi WebSocket Client
  → 监听 card.action.trigger 事件
  → 解析卡片动作类型和表单数据
  → 路由到 CommandRouter.handle_card_action()
  → 返回卡片更新或 toast 提示
```

## 8. 进程间通信

### 8.1 确定性通道（lark-oapi SDK）

```text
Python 主进程
  → lark-oapi Client 直接调用飞书 API
  → 无子进程开销
  → 返回结构化结果给编排层
```

### 8.2 确定性通道（lark-cli subprocess）

```text
Python 主进程
  → run_cli(["im", "+messages-send", ...], feishu_config)
  → subprocess.run(["lark-cli", ...], env={注入凭证})
  → 解析 stdout JSON 输出
  → 捕获 stderr 日志
  → 返回 CLIResult 给编排层
```

### 8.3 智能通道（Agent → ToolProvider）

```text
Python 主进程 (编排层)
  → 构建 AgentTask(description, context, complexity)
  → Agent Executor
    → LiteLLM completion(tools=tool_provider.to_litellm_tools())
    → tool_calls → ToolProvider.call_tool(name, args)
      → lark-oapi SDK → 飞书 API
      → 或 lark_cli.run → lark-cli subprocess → 飞书 API
      → 返回 tool result
    → Transport 归一化响应
    → 循环直到 Agent 完成
  → 返回 AgentResult 给编排层
```

### 8.4 事件流模式（长驻进程）

```text
lark-cli event +subscribe (长驻进程，环境变量注入凭证)
  → 事件写入 output-dir 目录
  → Python 主进程 watch 目录
  → 读取 NDJSON 文件
  → 解析并路由到事件处理器
```

### 8.5 卡片交互模式（WebSocket）

```text
lark-oapi WebSocket Client (长驻连接)
  → 接收 card.action.trigger 事件
  → Python 主进程解析卡片动作
  → 路由到 CommandRouter.handle_card_action()
  → 同步返回卡片更新指令
```

## 9. 目录结构

```text
teamflow/
├── docs/prd/                    # 产品需求文档
├── cli/                         # lark-cli 源码（参考学习，不直接引用）
├── skills/                      # SKILL.md 文件（Agent 能力描述）
│   ├── lark-approval/SKILL.md
│   ├── lark-im/SKILL.md
│   └── ...                      # 17 个 lark-* skill
├── src/
│   ├── teamflow/
│   │   ├── core/                # 核心领域枚举（ProjectStatus, WorkspaceStatus 等）
│   │   ├── access/              # 接入层
│   │   │   ├── watcher.py       # 事件文件监听
│   │   │   ├── dispatcher.py    # 事件去重与分发
│   │   │   ├── parser.py        # 消息/卡片事件解析
│   │   │   └── callback.py      # WebSocket 卡片交互回调
│   │   ├── orchestration/       # 业务编排层
│   │   │   ├── project_flow.py  # 项目创建状态机
│   │   │   ├── workspace_flow.py # 工作空间初始化编排
│   │   │   ├── command_router.py # 指令路由 + 卡片动作路由
│   │   │   ├── card_templates.py # 卡片模板
│   │   │   └── event_bus.py     # 内部事件总线
│   │   ├── execution/           # 执行层
│   │   │   ├── cli.py           # 确定性通道：lark-cli subprocess 封装
│   │   │   └── messages.py      # 消息发送/卡片更新（lark-oapi SDK）
│   │   ├── ai/                  # AI 层
│   │   │   ├── agent.py         # Agent executor：LiteLLM tool-use 循环
│   │   │   ├── tools/           # ToolProvider 工具系统
│   │   │   │   ├── __init__.py  # ToolProvider + ToolDef
│   │   │   │   └── feishu.py    # 飞书 API 工具（10+ 工具）
│   │   │   ├── transports/      # Transport 归一化层
│   │   │   │   ├── base.py      # ProviderTransport 抽象基类
│   │   │   │   ├── chat_completions.py # OpenAI 兼容格式
│   │   │   │   └── types.py     # NormalizedResponse / ToolCall / Usage
│   │   │   ├── model_registry.py # Model Registry（provider/模型元数据）
│   │   │   ├── models.py        # 模型路由（fast/smart/reasoning）与降级
│   │   │   ├── prompts.py       # 提示词管理（向后兼容）
│   │   │   └── skills/          # Skills 系统
│   │   │       └── __init__.py  # Skill + SkillRegistry + 自动发现
│   │   ├── scheduling/          # 调度层（定时任务，待实现）
│   │   ├── storage/             # 数据层
│   │   │   ├── models.py        # SQLModel 模型定义
│   │   │   └── repository.py    # Repository 封装
│   │   ├── config/              # 配置管理
│   │   │   └── settings.py      # YAML 读取 + 环境变量注入 + Pydantic 校验
│   │   ├── setup/               # 安装与初始化
│   │   │   ├── feishu.py        # 飞书应用创建/凭证配置
│   │   │   └── cli.py           # lark-cli 安装/验证
│   │   ├── main.py              # 主入口
│   │   └── __main__.py          # CLI 入口（setup/run/reset）
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── e2e/
├── scripts/
│   └── verify_agent.py          # Agent 集成验证脚本
├── pyproject.toml
├── config.example.yaml
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
│  │ - 接入层（事件监听 + 卡片回调）           │    │
│  │ - 业务编排层（双通道调度）                 │    │
│  │ - AI 层（Agent + ToolProvider + Skills） │    │
│  │ - 调度层                                  │    │
│  │ - 数据层 (SQLite)                        │    │
│  └───────┬─────────────────────────────────┘    │
│          │ subprocess                            │
│  ┌───────▼────────┐                             │
│  │ lark-cli       │                             │
│  │ (预编译 Go)    │                             │
│  │ · 事件订阅     │                             │
│  │ · CLI 透传     │                             │
│  └────────────────┘                             │
└──────────────────────────────────────────────────┘
```

### 10.2 进程管理

1. 主进程负责启动和监控一个长驻子进程：
   - lark-cli 事件订阅进程
2. Agent 通道零外部进程依赖（ToolProvider 直连 lark-oapi SDK）
3. 卡片回调通过 lark-oapi WebSocket 长连接接收（主进程内）
4. 短命令通过同步 subprocess.run 调用
5. lark-cli 二进制预安装

### 10.3 运行时依赖

| 依赖 | 安装方式 | 用途 |
|------|----------|------|
| lark-cli | `npm install -g @larksuite/cli` | 确定性通道 + 事件订阅 |
| Python 3.12+ | 系统安装 | 主进程 |

> **注意**：相比 MCP 方案，ToolProvider 方案去掉了 Node.js 运行时依赖和 MCP Server 子进程。

## 11. 关键设计决策

### 11.1 为什么选双通道而非全走 Agent

1. **性能**：发消息是高频操作，lark-oapi SDK 调用 50-100ms；走 Agent 需经 LiteLLM + ToolProvider，延迟高 1-2 个数量级
2. **成本**：每次 Agent 调用消耗 LLM token，发消息不需要 AI 判断
3. **确定性**：简单动作参数完全确定，不需要 AI 决策，避免幻觉风险
4. **可靠性**：确定性通道不依赖 LLM 服务可用性

### 11.2 为什么选 LiteLLM 自建循环而非 Agent 框架

1. **轻量**：TeamFlow 的 Agent 循环本质是 observe → think → act → observe，20 行代码
2. **灵活**：不绑定任何模型供应商，LiteLLM 支持 100+ 模型
3. **透明**：没有隐藏抽象，tool-use 循环完全可控可调试
4. **已选型**：LiteLLM 本身就在技术栈中，不引入新依赖

### 11.3 为什么从 MCP 切换到 ToolProvider

1. **协议不兼容**：飞书官方 MCP Server v0.5.1 的 `tools/list` 返回 Method not found
2. **零外部进程**：ToolProvider 是纯 Python，不需要启动 Node.js MCP Server 子进程
3. **SDK 直连**：lark-oapi SDK 是飞书官方 Python SDK，覆盖全量 OpenAPI
4. **调试简单**：Python 函数调用栈完整可追踪，比 stdio MCP 协议更容易调试
5. **可切换回**：MCP 方案待飞书官方修复后可平滑切换回，ToolProvider 接口兼容

### 11.4 为什么需要 Transport 层

1. **响应格式差异**：不同 LLM provider 的 tool_calls 格式、usage 字段、reasoning_content 等存在差异
2. **Reasoning 支持**：部分模型（DeepSeek-R1、o1 等）需要特殊的 reasoning 配置
3. **扩展性**：新增 provider 只需实现 ProviderTransport 接口
4. **归一化**：Agent Executor 只需处理 NormalizedResponse，不关心底层 provider 差异

### 11.5 为什么需要 Model Registry

1. **Provider 别名**：用户可能输入 glm、github 等别名，需要映射到标准 provider
2. **模型能力查询**：Agent Executor 需要知道模型是否支持 tool_call、reasoning 等
3. **LiteLLM 集成**：需要将 provider+model 映射为 LiteLLM 格式，配置环境变量和 base_url
4. **元数据丰富**：models.dev 提供模型参数量、context_window、成本等信息

### 11.6 为什么选 subprocess 而非 Go 共享库

1. **隔离性**：CLI 崩溃不影响主进程
2. **复用性**：直接复用 lark-cli 的 200+ 命令
3. **可调试性**：CLI 命令可独立运行和调试
4. **版本解耦**：CLI 可独立升级

### 11.7 为什么选 Python 而非全 Go

1. **AI 生态**：LiteLLM、lark-oapi SDK、提示词管理都在 Python 生态
2. **迭代速度**：业务逻辑和 AI 提示词需要快速迭代
3. **类型安全**：SQLModel + Pydantic 提供足够的类型保障

### 11.8 为什么用环境变量注入而非自定义 Go 扩展

1. **零编译**：不需要 fork lark-cli 源码和编译自定义二进制
2. **即时可用**：安装 lark-cli 即可使用，无需 Go 工具链
3. **维护简单**：lark-cli 升级时直接替换二进制

## 12. 性能考量

1. **确定性通道开销**：lark-oapi SDK 调用约 50-100ms，无子进程启动开销
2. **确定性通道开销（CLI）**：每次 CLI 调用约 50-100ms 启动时间，适合低频确定性动作
3. **智能通道开销**：Agent 单次任务 2-10 秒（取决于 LLM 响应和工具调用轮数），适合低频复杂任务
4. **事件吞吐**：文件监听模式下延迟在 100ms 以内
5. **并发控制**：确定性通道通过 asyncio 并发调度；智能通道控制并发 Agent 数避免 LLM 限流
6. **工具调用预算**：Agent 设置 `max_iterations`（默认 10），防止无限循环

## 13. 安全考量

1. **凭证隔离**：App Secret 仅存在于 config.yaml 和进程环境变量中
2. **日志脱敏**：config.yaml 加入 .gitignore；Agent 审计日志不含完整敏感输入
3. **进程隔离**：CLI 子进程崩溃不影响主进程；Agent 通道零外部进程
4. **Agent 权限控制**：通过 `allowed_tools` 白名单约束 Agent 可用工具；`lark_cli.run` 内置安全限制
5. **自治级别**：高风险动作（删除、移除成员）不加入 Agent 工具集，走确定性通道并需人工确认
6. **配置文件权限**：config.yaml 仅主进程用户可读

## 14. 演进方向

第一阶段以双通道架构为主。后续可根据需要演进：

1. **MCP 协议切换**：飞书官方 MCP Server 修复后，可从 ToolProvider 切换回 MCP，接口兼容
2. **远程 MCP 服务**：飞书远程 MCP 成熟后，替换本地工具实现
3. **自定义 Go 二进制**：需要深度定制凭证/监控时，fork lark-cli 编译增强版
4. **gRPC 模式**：将 CLI 改为长驻 gRPC 服务，减少进程启动开销
5. **流式 Agent**：Agent 执行过程中实时推送进度到飞书（卡片更新，已部分实现）
6. **分布式部署**：主进程和执行层分离部署，通过消息队列通信

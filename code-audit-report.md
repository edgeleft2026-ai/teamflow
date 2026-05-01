# TeamFlow 代码审计报告

> **审计日期**：2026-05-01  
> **审计范围**：`src/teamflow/` 全部 Python 源码，含 access、orchestration、ai、execution、git、storage、config、core、setup 模块  
> **项目版本**：v0.1.0（M0-M2 已完成，M3 未开始）

---

## 目录

1. [总体评估](#1-总体评估)
2. [架构审计](#2-架构审计)
3. [模块逐层审计](#3-模块逐层审计)
4. [技术债务清单](#4-技术债务清单)
5. [安全审计](#5-安全审计)
6. [测试与质量保障](#6-测试与质量保障)
7. [CI/CD 与部署](#7-cicd-与部署)
8. [优化建议路线图](#8-优化建议路线图)

---

## 1. 总体评估

### 评分卡

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | B+ | 分层清晰，双通道设计合理，但存在循环依赖隐患 |
| 代码质量 | B- | 大部分代码规范，但异常处理不一致，类型标注不完整 |
| 安全 | C+ | 日志脱敏已实现，但 config.yaml 含明文密钥在代码仓库中 |
| 测试覆盖 | D | `src/tests/` 目录不存在，零单元测试 |
| CI/CD | F | 无任何 CI/CD 配置 |
| 文档 | B | PRD 文档齐全，但缺 README 和行内注释 |
| 可观测性 | B- | 日志系统完善，缺 metrics/tracing |
| **综合** | **C+** | 核心链路可用但工程化严重不足 |

### 关键发现

1. **架构债务**：access → orchestration → execution 三层单向依赖约束被多处反向调用打破（`access/callback.py` 直接导入 `orchestration/command_router.py`）
2. **零测试**：`src/tests/` 目录不存在，仅有 `scripts/` 下的手动验证脚本
3. **配置泄露**：`config.yaml` 包含完整的 app_secret、access_token 等敏感信息
4. **异常吞没**：多个关键路径使用 `except Exception: logger.exception()` 后继续执行，无降级/补偿机制
5. **线程安全隐患**：SQLite 在多线程场景下使用共享 Session，`project_flow.py` 在独立线程中创建新 Session 实例

---

## 2. 架构审计

### 2.1 当前架构

```
接入层 (access/)
├── parser.py      — NDJSON 事件解析（226 行）
├── dispatcher.py  — 事件分发 + 去重（138 行）
├── watcher.py     — 文件系统轮询（105 行）
├── callback.py    — WebSocket 卡片回调（121 行）
└── feishu_contact.py — 通讯录服务（208 行）

编排层 (orchestration/)
├── command_router.py    — 消息/卡片路由分发
├── project_flow.py      — 项目创建流程状态机（618 行）
├── workspace_flow.py    — 工作空间初始化（823 行）
├── access_sync.py       — 权限同步（360 行）
├── event_bus.py         — 事件总线
├── card_templates.py    — 卡片模板
└── batch_register.py    — 批量注册

AI 层 (ai/)
├── agent.py             — Agent 执行器（352 行）
├── tools/               — 工具提供者
├── skills/              — 技能系统（22 个 skill）
├── transports/          — 传输层抽象
├── models.py            — 模型路由
├── model_registry.py    — 模型注册表（690 行）
└── prompts.py           — 提示词模板

执行层 (execution/)
├── cli.py               — lark-cli subprocess 封装（232 行）
└── messages.py          — 消息发送便捷函数（209 行）
```

### 2.2 架构优势

**分层设计清晰**：四层模型（接入→编排→执行/AI）为正确的关注点分离奠定了基础，文档描述的"三层单向依赖"原则是好的设计意图。

**双通道执行**：确定性通道（lark-cli subprocess）与智能通道（Agent + ToolProvider）的分离设计合理，各司其职。

**Skills 系统设计优秀**：插件式 `Skill` 注册 + `SKILL.md` 文件驱动自动发现是一个精心设计的可扩展架构，22 个飞书 skill 已内置，扩展成本低。

**Transport 层抽象**：`ProviderTransport` 抽象基类 + `ChatCompletionsTransport` 实现，为多 LLM Provider 支持提供了清晰的扩展点。

### 2.3 架构问题

#### 问题 1：循环依赖 / 层级违规

**严重程度**：中

```
access/callback.py
  └── imports orchestration/command_router.py   ← 接入层反向依赖编排层

orchestration/project_flow.py
  └── imports access/parser.py (CardActionData)  ← 编排层依赖接入层数据类型
```

接入层不应该直接导入编排层的具体实现。`CardActionData` 等共享类型应提取到 `core/types.py`。

**建议**：创建 `core/types.py` 存放跨层共享的数据结构（`CardActionData`、`ChatMemberEventData`），各层仅依赖 `core/types`。

#### 问题 2：配置模块位置不一致

**严重程度**：低

- CLAUDE.md 描述配置在 `config/`，但实际路径是 `src/teamflow/config/settings.py`
- `core/config.py` 不存在（文档提及但未实现）
- 这导致项目描述与实现不一致

**建议**：统一文档与实际结构，或创建 `core/config.py` 作为配置的门面。

#### 问题 3：SQLite + 多线程风险

**严重程度**：高

- `project_flow.py` 在 `threading.Thread` 中创建新的 SQLAlchemy Session
- `workspace_flow.py` 使用 `asyncio.create_task` + `with self.session_factory()`
- SQLite 默认不支持并发写，多个线程同时操作可能触发 `SQLITE_BUSY`
- `access_sync.py` 中 `on_member_added` 通过 `asyncio.create_task` 异步化，但内部使用同步 `get_session()`

**建议**：
1. 短期：设置 SQLite `check_same_thread=False` + WAL 模式 + `busy_timeout=5000`
2. 中期：引入连接池（如 `sqlalchemy.pool.QueuePool`）或迁移至 PostgreSQL
3. 长期：M3 推进时任务/观察数据量增大，SQLite 将成为瓶颈

#### 问题 4：会话管理分散

**严重程度**：中

Session 的生命周期管理分散在多处：
- `project_flow.py` 构造函数接受 `Session` 参数（调用者管理）
- `workspace_flow.py` 使用 `session_factory` 工厂（内部管理）
- `access_sync.py` 在方法内部调用 `get_session()`
- `repository.py` 假设调用者已管理事务

三种模式混用增加了 Session 泄漏和事务边界不清晰的风险。

**建议**：统一为 `session_factory` 模式，通过 `@contextmanager` 或依赖注入确保 Session 生命周期一致。

#### 问题 5：超大文件

**严重程度**：中

| 文件 | 行数 | 问题 |
|------|------|------|
| `workspace_flow.py` | 823 | Agent + 降级 + 进度更新混在一起 |
| `project_flow.py` | 618 | 文本流 + 表单流 + Gitea 创建耦合 |
| `model_registry.py` | 690 | 数据（provider/models）与逻辑混合 |
| `setup/cli.py` | 944 | 超过 900 行交互式向导代码 |

**建议**：
- `workspace_flow.py` → 拆分为 `workspace_agent.py` + `workspace_deterministic.py` + `workspace_reporter.py`
- `model_registry.py` → 将 Provider/Model 数据提取到 `model_data.py`（纯数据文件）
- `setup/cli.py` → 拆分为 provider 配置、飞书配置、Gitea 配置三个模块

---

## 3. 模块逐层审计

### 3.1 接入层 (access/)

#### parser.py — **评分 B+**

优点：
- 清晰的数据类定义（`FeishuEvent`、`CardActionData`、`ChatMemberEventData`）
- 兼容 `lark-cli` compact 格式和标准 SDK 格式

问题：
- `parse_ndjson_line` 使用 `json.loads` 裸解析，对大 payload（如消息中的附件）无大小上限保护
- `ChatMemberEventData.open_ids` 提取逻辑在多个字段间试探（`ev.get("users")` / `ev.get("data", {}).get("users")` / `ev.get("user_id")`），应抽象为独立的 `_extract_user_ids()` 函数
- 缺少对事件 schema 版本变化的版本号检查

#### dispatcher.py — **评分 B**

优点：
- 事件去重机制（内存 + 磁盘持久化）
- 支持类型处理器和全局处理器两种模式

问题：
- 去重使用简单 `set`，达到 `dedup_max_size` 时清除一半的方式丢失事件 ID，可能引入少量重复事件
- 应该使用 LRU 缓存（如 `functools.lru_cache` 或 Redis）代替手工 set 管理
- `_pending_shard` 字段（第 47 行）定义了但从未使用——死代码

#### watcher.py — **评分 C+**

优点：
- 轮询方案简单有效
- 支持 NDJSON 和 JSON 两种输出格式

问题：
- **轮询方式效率低**：每 0.5 秒扫描目录，高事件量时延迟增大
- **使用 `rglob` 递归扫描**：目录下文件增多时 I/O 开销线性增长
- 应使用 OS 级文件变更通知（`watchdog` 库或 `inotify`/`ReadDirectoryChangesW`）
- `multiline` 模式每次读取整个 JSON 文件（不是逐行），大文件会导致内存问题

#### callback.py — **评分 B**

优点：
- WebSocket 回调在 daemon 线程中运行，不阻塞主循环
- 正确处理 `P2CardActionTrigger` 结构

问题：
- WebSocket 断连后无自动重连机制（飞书 SDK 的 `ws.Client.start()` 是否内置重连？）
- 与 `access/parser.py` 中的 `extract_card_action_data` 在 `CardActionData` 构建上有代码重复
- 回调线程异常会静默终止 daemon 线程，无告警

### 3.2 编排层 (orchestration/)

#### project_flow.py — **评分 B-**

优点：
- 文本流和表单流两种创建路径覆盖完整
- 进度卡片渐进式更新，用户体验好
- 单步失败不阻断后续步骤

问题：
1. **状态机实现脆弱**：使用字符串常量 `STATE_COLLECTING_NAME` 等，应使用 Enum
2. **`_auto_create_repo` 调用 `asyncio.run()` 在同步函数中**：在已有事件循环的上下文中会抛出 `RuntimeError: This event loop is already running`
3. **Worker 线程无超时控制**：`_start_submission_worker` 启动的后台线程可能无限运行
4. **Gitea 仓库创建失败静默**：`_auto_create_repo` 捕获所有异常后返回 `None`，不向上传播
5. **步骤定义冗长**：`_build_initial_steps()` 中 11 个步骤硬编码，应数据驱动

#### workspace_flow.py — **评分 C+**

优点：
- Agent 主通道 + 确定性 Fallback 的设计稳健
- 支持实时进度卡片更新（`report_step` 回调）
- 幂等保护（检查 `workspace_status`）

问题：
1. **文件过长（823 行）**：混合了 Agent 执行、降级逻辑、步骤管理、卡片更新、事件发布
2. **Agent 结果解析脆弱**：`_parse_agent_result` 用正则从文本中提取 chat_id/doc_url，依赖 Agent 输出格式稳定
3. **降级通道覆盖不完整**：Agent 失败后，降级通道重试已成功的步骤（如群已创建但 Agent 未解析出 chat_id）
4. **`_get_admin_chat_id` 通过搜索群名匹配**：群名可能重名，应通过群 ID 精确查找
5. **步骤状态同步复杂**：`_upsert_step` + `_sync_submission_card` 在多个 exit 点重复调用

#### access_sync.py — **评分 B**

优点：
- 成员进出事件处理完整
- 自动邮箱匹配降级绑定身份
- 异常不抛出，不影响主流程

问题：
1. **每次操作创建新的 `GiteaService` 实例**：`add_team_member` 和 `remove_team_member` 各自创建并关闭 httpx 客户端，应复用
2. **电话本 API 调用同步阻塞**：`_get_feishu_user_email` 使用 httpx 但运行在 asyncio 事件循环中
3. **权限同步没有限流/重试**：成员大量进出时可能触发 Gitea API 限流

### 3.3 AI 层 (ai/)

#### agent.py — **评分 B+**

优点：
- 完整的 tool-use 循环，错误处理覆盖超时、达到上限、常规异常
- 模型能力自动检测和 reasoning 配置注入
- Skill 自动匹配和 prompt 注入

问题：
1. **`_resolve_model` 的模型解析逻辑与 `model_registry.py` 有重复**：模型字符串解析（`_parse_provider_n_model`）应该在 registry 层统一
2. **LiteLLM 调用无重试机制**：网络抖动导致的瞬时错误直接向上抛出
3. **`max_iterations` 仅靠计数限制**：无 token 消耗监控，对需要大量 context 的任务可能超出预算

#### tools/feishu.py — **评分 B**

优点：
- 10 个工具函数，覆盖 IM、Doc、Drive、Bot API
- 完整的 JSON Schema 定义
- `lark_cli.run` 透传覆盖未封装 API

问题：
1. **全局 `feishu_client` 变量**：是单例模式但无线程安全保护
2. **`_run_lark_cli` 使用同步 subprocess**：在 async 工具调用中阻塞事件循环
3. **工具 Schema 中无 `additionalProperties: false`**：Agent 可能传入未定义的参数

#### transports/ — **评分 B+**

优点：
- 抽象基类设计合理，扩展点清晰
- `NormalizedResponse` 统一了多 Provider 响应格式
- 支持 reasoning_content、cache_stats 等高级特性

问题：
1. **当前仅有 `ChatCompletionsTransport` 一个实现**：文档提及的 `AnthropicMessagesTransport` 未实现
2. **`convert_messages` 默认实现假设已为 OpenAI 格式**：非 OpenAI Provider 需要 override，但基类未标记为抽象方法

#### skills/ — **评分 A-**

优点：
- 插件式设计优秀，SKILL.md 文件驱动自动发现
- 支持 trigger 正则匹配、prompt 注入、工具约束
- 17 个飞书 skill 已内置

问题：
1. **Skill 加载一次全量**：22 个 SKILL.md 文件全部解析，未来增长后需要考虑懒加载
2. **SKILL.md 的 YAML frontmatter 解析**：自定义 parser（`_parse_frontmatter`）而不是使用 `python-frontmatter` 标准库
3. **skill 的 context 变量插值**：`{project_name}` 等变量的插值逻辑分散在 `Skill.apply()` 和 `AgentExecutor` 中

### 3.4 存储层 (storage/)

#### repository.py — **评分 B-**

优点：
- Repository 模式封装了数据库访问
- 每个 Repository 做单一职责

问题：
1. **缺少 `RepositoryException` 异常体系**：底层 SQLAlchemy 异常直接传播到调用方
2. **`get_session()` 的 `__exit__` 时 commit**：长事务可能导致锁竞争，缺少只读 session 概念
3. **无数据迁移机制**：模型变更时依赖 `SQLModel.metadata.create_all()` 只能创建新表，不能 ALTER
4. **`ConversationStateRepo.upsert` 不是原子操作**：先 `get_active` 再 upsert，存在竞态条件
5. **`ProjectMemberRepo.add` 同样存在竞态**：先 `get_active` 再操作

### 3.5 执行层 (execution/)

#### cli.py — **评分 B-**

优点：
- tenant_access_token 自动交换 + 缓存
- 结构化 `CLIResult` 输出
- 跨平台 CLI 二进制查找

问题：
1. **`_exchange_tenant_token` 使用 `urlopen`（同步）**：调用方在 async 上下文中会被阻塞
2. **Token 缓存无持久化**：进程重启后需要重新获取 token
3. **`find_cli_binary` 搜索路径硬编码**：应支持 `TEAMFLOW_CLI_BINARY` 环境变量覆盖（已在 main.py 中处理但 cli.py 自身不支持）

#### messages.py — **评分 C+**

优点：
- 提供了 async wrapper 适配异步场景
- `update_card_message` 使用 lark-oapi SDK 而非 CLI

问题：
1. **`update_card_message` 每次调用创建新的 `lark.Client`**：应复用全局 client 实例
2. **`send_message` 的 ID 参数同时接受 `chat_id` 和 `user_id`**：虽内部有逻辑限制，但类型签名未表达"互斥"语义
3. **async wrappers 使用 `asyncio.to_thread`**：每个调用都创建新线程，高频场景应使用 `ThreadPoolExecutor`

---

## 4. 技术债务清单

按解决优先级排序：

### P0 — 阻塞项（M3 启动前必须解决）

| ID | 问题 | 模块 | 解决方案 |
|----|------|------|----------|
| TD-01 | **零单元测试** | 全局 | 建立 `src/tests/` 目录，为核心模块编写测试 |
| TD-02 | **SQLite 多线程写入冲突** | storage/database.py | 启用 WAL 模式 + busy_timeout，或迁移 PostgreSQL |
| TD-03 | **config.yaml 含明文密钥** | config.yaml | 移出仓库，仅保留 config.example.yaml |
| TD-04 | **asyncio.run() 在事件循环中调用** | project_flow.py:257 | 改为 await gitea.create_repo_async() |

### P1 — 高优先级（1-2 周内）

| ID | 问题 | 模块 | 解决方案 |
|----|------|------|----------|
| TD-05 | **循环导入/层级违规** | access/callback.py | 底层 register 模式或事件回调解耦 |
| TD-06 | **异常吞没无补偿** | 多处 | 引入 Result 类型或明确的错误处理策略 |
| TD-07 | **Session 生命周期不一致** | 多处 | 统一为 session_factory 注入模式 |
| TD-08 | **workspace_flow.py 823 行** | orchestration/ | 拆分为 3-4 个文件 |
| TD-09 | **无数据迁移机制** | storage/ | 引入 Alembic |
| TD-10 | **watcher 使用轮询** | access/watcher.py | 替换为 watchdog 库 |

### P2 — 中优先级（1 月内）

| ID | 问题 | 模块 | 解决方案 |
|----|------|------|----------|
| TD-11 | **GiteaService 每次创建新实例** | access_sync.py | 实例复用或对象池 |
| TD-12 | **WebSocket 回调无重连** | access/callback.py | 添加指数退避重连 |
| TD-13 | **Agent 结果解析脆弱** | workspace_flow.py | 结构化 Agent 输出（要求 JSON） |
| TD-14 | **LiteLLM 调用无重试** | ai/agent.py | 添加 exponential backoff 重试 |
| TD-15 | **model_registry.py 690 行** | ai/model_registry.py | 数据提取到独立 JSON/YAML 文件 |
| TD-16 | **全局 feishu_client 无线程安全** | ai/tools/feishu.py | 使用 threading.local() 或 asyncio 锁 |

### P3 — 低优先级（M3 后期）

| ID | 问题 | 模块 | 解决方案 |
|----|------|------|----------|
| TD-17 | **缺少 README.md** | 根目录 | 编写项目 README |
| TD-18 | **无 Metrics/Dashboard** | 全局 | 引入 Prometheus metrics 端点 |
| TD-19 | **无请求级 Tracing** | 全局 | 引入 OpenTelemetry（当前有 correlation_id 打底） |
| TD-20 | **Skills 全量加载** | ai/skills/ | 按需懒加载 |
| TD-21 | **Token 缓存无持久化** | execution/cli.py | 写入文件缓存，进程重启复用 |

---

## 5. 安全审计

### 5.1 密钥管理

**🔴 严重：config.yaml 包含明文凭据**

```yaml
feishu:
  app_secret: EoDDsfIlUUg8Mn0rgqzNdbz3iVFuxeUy  ← 真实密钥在仓库中
gitea:
  access_token: f59f5e18afeabe006de5d0f1a3ee7e959b53d680  ← 真实令牌
agent:
  provider: minimax-cn
  fast_model: minimax/MiniMax-M2.7       ← 暴露内部模型选择
```

config.yaml 虽然在 `.gitignore` 中，但当前存在于工作目录。需确认：
1. 是否已通过 `git rm --cached` 从 Git 历史中移除
2. 是否已在飞书和 Gitea 后台轮换这些密钥

**建议**：
1. 立即轮换所有暴露的密钥
2. 使用 `.env` 文件 + `python-dotenv` 管理敏感配置
3. 添加 `.env.example` 模板文件
4. 在 CI 中运行 `detect-secrets` 或 `truffleHog` 扫描

### 5.2 日志脱敏

**🟢 已实现**：`core/logging.py` 中的 `SensitiveFilter` 自动脱敏 `app_secret`、`access_token` 等字段。

TODO.md 中标记为未完成（"日志中没有密钥或访问令牌"），但代码已实现 `SensitiveFilter`。建议通过自动化测试验证脱敏效果。

### 5.3 输入验证

**🟡 需改进**：

- `project_flow.py` 中对 `project_name` 仅检查非空，无长度/字符限制
- `parser.py` 中 `parse_ndjson_line` 无 payload 大小限制
- Agent tool 调用无参数校验（依赖 LLM 生成正确参数）

**建议**：在 Repository 层添加 Pydantic 验证，在事件解析层添加 payload 大小上限（如 10MB）。

### 5.4 API 调用安全

**🟢 基本合规**：
- tenant_access_token 自动交换，60s 安全边距
- lark-cli 子进程凭据通过环境变量注入，不出现命令行参数中
- Agent max_iterations 限制防止无限循环

**🟡 需改进**：高风险操作为 Agent 工具（如 `add_document_collaborator`），应添加人工确认机制。

---

## 6. 测试与质量保障

### 6.1 现状

| 测试类型 | 状态 | 说明 |
|----------|------|------|
| 单元测试 | **零** | `src/tests/` 目录不存在 |
| 集成测试 | **零** | 无框架配置 |
| E2E 测试 | 1 个脚本 | `scripts/e2e_test.py`（需真实飞书/Gitea 凭据） |
| 验证脚本 | 3 个 | `verify_agent.py`、`test_agent.py`、`test_feishu_contacts.py` |
| 代码检查 | Ruff 配置 | `pyproject.toml` 中存在但未集成到 CI |

### 6.2 建议测试策略

```
src/tests/
├── unit/
│   ├── test_parser.py          # FeishuEvent 解析
│   ├── test_project_flow.py    # 状态机转换
│   ├── test_repository.py      # CRUD 操作
│   ├── test_cli.py             # token 交换、缓存
│   ├── test_model_registry.py  # 模型路由
│   └── test_event_bus.py       # 事件发布/订阅
├── integration/
│   ├── test_agent_loop.py      # Agent + 真实 LLM
│   ├── test_gitea_service.py   # Gitea API 交互
│   └── test_database.py        # SQLite 并发写入
└── fixtures/
    ├── events/                 # 飞书事件 NDJSON 样本
    └── cards/                  # 卡片回调样本
```

**关键测试用例（优先编写）**：
1. `test_project_create_idempotent` — 同一 event_id 不创建重复项目
2. `test_token_cache_expiry` — token 过期前后重新获取
3. `test_workspace_init_idempotent` — 重复触发不创建重复群/文档
4. `test_session_rollback_on_error` — 异常时事务正确回滚
5. `test_agent_max_iterations_limit` — Agent 达到上限时正确终止

---

## 7. CI/CD 与部署

### 7.1 现状

**🟡 接近空白**：无 Dockerfile、无 docker-compose、无 GitHub Actions、无部署配置。

### 7.2 建议 CI/CD 流水线

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v2
      - run: ruff check src/
      - run: ruff format --check src/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev]"
      - run: pytest src/tests/ --cov=src/teamflow --cov-report=xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install detect-secrets
      - run: detect-secrets scan --all-files
```

### 7.3 建议 Docker 化

```dockerfile
# Dockerfile 建议结构
FROM python:3.12-slim
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g @larksuite/cli
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
CMD ["teamflow", "run"]
```

---

## 8. 优化建议路线图

### 第一阶段：工程基础（2-3 周）

```
Week 1-2: 测试基础设施
├── 建立 src/tests/ 目录结构
├── 编写核心模块单元测试（P0 列表）
├── 集成 pytest + coverage 到开发流程
└── 配置 CI（Ruff + Pytest）

Week 2-3: 安全加固
├── 轮换泄露的密钥
├── 将 config.yaml 迁移为 .env 管理
├── 添加 .env.example
└── 添加 detect-secrets 扫描

Week 3: 数据库加固
├── 启用 SQLite WAL 模式
├── 确认检查 same_thread=False 配置
├── 统一 Session 管理为 session_factory 模式
└── 移除 asyncio.run() 嵌套调用
```

### 第二阶段：架构优化（2-4 周）

```
Week 4-5: 模块拆分
├── workspace_flow.py → 3 文件拆分
├── model_registry.py → 数据/逻辑分离
├── project_flow.py → 状态机提取
└── 解决 access ↔ orchestration 循环依赖

Week 5-6: 容错增强
├── Agent 结果要求结构化 JSON 输出
├── LiteLLM 调用添加重试
├── WebSocket 回调添加断线重连
├── GiteaService 实例复用
└── 统一异常处理策略

Week 6-7: 可观测性
├── 添加 Prometheus metrics 端点（/metrics）
├── 引入 Alembic 数据迁移
└── 替换 watcher 轮询为 watchdog
```

### 第三阶段：M3 就绪（1-2 周）

```
Week 8-9: M3 前置准备
├── 设计 Task/Observation/Decision 数据模型
├── 实现 Alembic 迁移脚本
├── 编写 M3 功能的集成测试框架
├── Docker 化部署
└── 编写 README.md
```

---

## 附录：快速修复清单

以下是可以在单个 PR 中完成的低风险改进：

- [ ] `orchestration/enums.py`：将字符串状态常量改为 Enum
- [ ] 删除 `access/dispatcher.py:47` 的死代码 `_pending_shard`
- [ ] 删除 `config.yaml` 中的真实凭据并轮换密钥
- [ ] 在 `storage/database.py` 添加 `connect_args={"check_same_thread": False}` 和 `"busy_timeout": 5000`
- [ ] 在 CI 中集成 Ruff check
- [ ] 添加 `.env.example` 模板
- [ ] 修正 CLAUDE.md 中 `storage/repositories.py`（复数）→ `storage/repository.py`（单数）
- [ ] 修正 CLAUDE.md 中 `access/card_handler.py` → 实际不存在
- [ ] 修正 CLAUDE.md 中 `core/exceptions.py` → 实际不存在
- [ ] 在 `update_card_message` 中复用全局 lark-oapi client

---

> **总结**：TeamFlow 的核心链路已经跑通，架构方向正确，Skills 系统和 Transport 层的设计值得肯定。但**工程化严重不足**——零测试、无 CI/CD、密钥泄露是最紧迫的问题。以当前状态进入 M3，SQLite 写入冲突和 asyncio.run() 嵌套将直接导致运行时故障。建议先投入 3-4 周完成"第一阶段：工程基础"后再推进 M3。

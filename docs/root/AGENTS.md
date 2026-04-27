# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

TeamFlow AI 是一个 AI 驱动的项目管理助手，通过感知-决策-行动循环自动监控项目健康度、识别风险并执行操作。核心集成飞书（Feishu/Lark）进行通知和协作。

## Common Commands

```bash
# 启动服务
python run.py                          # 直接 uvicorn 启动（开发热重载）
teamflow run --port 8000               # CLI 启动（带 curses dashboard）
teamflow setup                         # 交互式配置向导
teamflow setup model                   # 配置 LLM 提供商
teamflow setup feishu                  # 配置飞书集成
teamflow doctor                        # 诊断配置问题
teamflow config show                   # 查看当前配置

# 测试
python -m pytest tests/                # 运行全部测试
python -m pytest tests/test_unit.py    # 单文件测试
python -m pytest tests/test_unit.py::TestClassName::test_method -v  # 单个测试

# Docker
docker compose up -d                   # 容器启动

# 依赖安装
pip install -r requirements.txt
pip install -e .                       # 可编辑安装（注册 teamflow CLI 命令）
```

## Architecture

采用 **感知 → 决策 → 行动** 三层架构，核心数据流为：

```
Perception (事件发布) → DecisionEngine (规则/策略/LLM 三级匹配) → Action (执行)
```

### 核心模块

- **`app/core/agent.py`** — AIAgent，中央协调器，订阅 EventBus 全部事件，委托 DecisionEngine 处理
- **`app/core/decision.py`** — DecisionEngine，按优先级匹配：规则引擎(`rules.py`) → 策略引擎(`strategy.py`) → LLM 兜底分析，并根据自治级别（auto/approval/forbidden）决定是否自动执行
- **`app/perception/event_bus.py`** — 异步事件总线，支持按类型订阅和全局订阅
- **`app/core/strategy.py`** — 策略引擎，从 `strategies/active/` 加载 YAML frontmatter 的 Markdown 文件，支持 AST 安全条件评估、模板渲染、效果追踪和自动归档
- **`app/core/llm/`** — LLM 多提供商抽象层（OpenAI/Anthropic 兼容），工厂模式，支持模型分层（fast/smart/reasoning）
- **`app/actions/`** — Action 基类 + 具体实现，每个 Action 接收 Event 和 context，返回 ActionResult

### 飞书集成

- **`app/feishu/`** — 飞书客户端，支持 WebSocket（推荐）和 Webhook 两种连接模式
- **`app/feishu/message_batch.py`** — 消息批处理，合并短时间内的多条通知
- **`app/feishu/message_filter.py`** — 消息过滤（bot 自身消息、重复消息）
- **`app/feishu/rich_message.py`** — 富文本消息构建

### 定时任务

- **`app/scheduler/manager.py`** — APScheduler 封装，从 `config/default.yaml` 的 `scheduler.jobs` 读取配置，使用文件锁防多实例
- **`app/scheduler/jobs.py`** — JOB_REGISTRY 注册所有定时任务（daily_standup, overdue_scan, git_activity_scan, health_check, weekly_report 等）

### 数据层

- **`app/database.py`** — SQLite（WAL 模式），线程安全，自动重试写操作。全局单例通过 `get_db()` 获取
- **`app/config.py`** — YAML 配置 + 环境变量模板（`${VAR:default}` 格式），Pydantic 模型校验。全局单例通过 `get_settings()` 获取

### 辅助子系统

- **`app/core/credential_pool.py`** — 多 API Key 轮转池
- **`app/core/llm_tracker.py`** — LLM 调用追踪和成本统计
- **`app/core/health.py`** — 项目健康度评分
- **`app/core/memory.py` / `memory_enhanced.py`** — 对话记忆管理
- **`app/core/strategy_evolution.py`** — 策略效果追踪和自动演化
- **`app/core/audit.py`** — 审计日志

## Key Patterns

- **全局单例**：所有核心组件（Database, Settings, EventBus, AIAgent, DecisionEngine, SchedulerManager 等）通过 `get_*()` 函数获取，模块级变量持有实例
- **策略文件格式**：`strategies/active/*.md`，YAML frontmatter 定义元数据（trigger, condition, action, autonomy, effectiveness），正文包含消息模板。condition 使用 AST 解析而非 eval
- **自治级别**：每个动作有 autonomy 标签（`auto` 自动执行 / `approval` 需审批 / `forbidden` 禁止），由 `AutonomyConfig` 控制
- **Action 注册表**：`decision.py` 中的 `_ACTION_REGISTRY` 字典，按 name 查找 Action 实例

## Configuration

- `config/default.yaml` — 默认配置，支持 `${ENV_VAR:default}` 模板
- `.env` — 环境变量（不入 Git）
- `config/rules.yaml` — 规则定义
- `prompts/*.md` — LLM prompt 模板（standup, risk_analysis, weekly_report 等）

## Testing Notes

测试位于 `tests/` 目录，使用 pytest。测试通过 mock 飞书和 LLM 调用来避免外部依赖。环境需要 Python >= 3.11。

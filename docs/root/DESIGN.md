# TeamFlow AI 设计说明

## 目标

TeamFlow AI 是一个无前端、后端优先的 AI 项目管理助手。它持续观察项目状态，自动识别风险，并通过飞书推动协作。

核心循环：

```text
Perception → EventBus → AIAgent → DecisionEngine → Action
```

## 架构

### 感知层

- `GitMonitor`：采集 commit、分支、贡献者和分支滞后信息。
- `TaskMonitor`：扫描逾期、停滞、阻塞、成员负载、优先级倒置和里程碑风险。
- `EventBus`：统一发布和订阅事件。

### 决策层

`DecisionEngine` 使用三层匹配：

1. 规则引擎：适合确定性事件，例如逾期提醒。
2. 策略引擎：从 `strategies/active/*.md` 加载可演进策略。
3. LLM fallback：分析未匹配事件，并可生成待审批策略。

自治级别：

- `auto`：直接执行低风险动作。
- `approval`：记录决策并等待审批。
- `forbidden`：拒绝执行。

### 行动层

Action 通过统一接口执行外部动作。当前核心 Action：

- 飞书通知：个人、团队、管理员。
- 飞书文档：创建和更新文档。
- 飞书任务：创建、完成、搜索、本地同步。
- 飞书日历：创建日程、查询空闲、推荐时间。
- 飞书审批：创建、通过、拒绝、查询。
- 邮件、观察日志、重分配建议。

### 数据层

SQLite 使用 WAL 模式，保存：

- 项目、成员、任务、任务依赖、里程碑。
- Git 快照、观察记录、决策记录。
- 对话和会话上下文。

## 调度

调度器基于 APScheduler，并使用跨平台文件锁避免多实例重复运行。默认任务覆盖日常站会、周报、健康评分、Git 活动扫描、任务风险扫描、里程碑扫描和策略维护。

## 飞书集成

支持 WebSocket 和 Webhook 两种模式。测试默认使用 mock，不依赖真实租户。真实接入需要配置：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

## 运行与可观测性

- `/health`：轻量健康检查。
- `/health/detailed`：详细运行状态，包括 DB、调度器、飞书连接、凭据池和 LLM 统计。
- `data/runtime.json`：运行状态快照，便于外部监控读取。
- `data/llm_usage_report.json`：LLM 调用统计。

## 当前边界

- `sub_agent` 当前是并发项目巡检器，不是真正隔离的多代理运行时。
- 富媒体、交互卡片和复杂审批表单属于后续增强。
- 策略自进化当前覆盖记录、降级和归档，自动改写策略内容可继续增强。

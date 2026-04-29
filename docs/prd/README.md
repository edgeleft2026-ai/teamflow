# TeamFlow PRD 导航

本目录承载 TeamFlow 当前阶段的正式产品需求文档。文档目标是把产品方向、MVP 范围、模块边界、数据事件、验收标准和测试方式收敛到同一套可执行规格中。

## 阅读顺序

建议按以下顺序阅读：

1. [产品总纲](./00-product-overview.md)：理解产品定位、阶段目标、核心闭环和模块划分。
2. [MVP 范围](./01-mvp-scope.md)：明确第一阶段必须交付、暂不交付和里程碑边界。
3. [技术架构](./06-technical-architecture.md)：理解双通道架构（Python 主进程 + 确定性通道/Agent 智能通道）的技术选型和集成方式。
4. [模块 PRD](./modules/01-project-entry-and-onboarding.md)：逐个理解业务模块的输入、输出、规则和验收要求。
5. [数据与事件模型](./02-data-and-event-model.md)：对齐开发需要的核心对象、状态、事件 payload 和幂等规则。
6. [验收清单](./03-acceptance-checklist.md)：按场景验证是否满足交付标准。
7. [测试策略](./04-testing-strategy.md)：指导本地、集成和真实飞书环境下的验证方式。
8. [提示词模板](./05-prompt-templates.md)：维护第一阶段 AI 输出所需的基础提示词。

## 文档结构

### 产品级文档

1. [00-product-overview.md](./00-product-overview.md)
2. [01-mvp-scope.md](./01-mvp-scope.md)
3. [02-data-and-event-model.md](./02-data-and-event-model.md)
4. [03-acceptance-checklist.md](./03-acceptance-checklist.md)
5. [04-testing-strategy.md](./04-testing-strategy.md)
6. [05-prompt-templates.md](./05-prompt-templates.md)
7. [06-technical-architecture.md](./06-technical-architecture.md)

### 模块 PRD

1. [01-project-entry-and-onboarding.md](./modules/01-project-entry-and-onboarding.md)
2. [02-feishu-workspace.md](./modules/02-feishu-workspace.md)
3. [03-project-operations-and-collaboration.md](./modules/03-project-operations-and-collaboration.md)
4. [04-ai-analysis-and-decision.md](./modules/04-ai-analysis-and-decision.md)
5. [05-platform-and-observability.md](./modules/05-platform-and-observability.md)

## 模块关系

TeamFlow 的第一阶段主链路为：

```text
飞书消息接入
  -> 项目创建引导
  -> 项目记录落库
  -> project.created
  -> 飞书群和项目文档初始化
  -> project.workspace_initialized
  -> 项目运行期提醒、汇报和查询
```

模块职责如下：

1. 项目入口与初始化：负责用户触发、信息收集、项目落库和 `project.created` 发布。
2. 飞书工作空间：负责响应项目创建事件，创建项目群、项目文档并返回初始化结果。
3. 项目运行与协作：负责风险提醒、站会摘要、周报、状态查询和消息路由。
4. AI 分析与决策：负责规则、策略、AI 分析的分层决策，以及输出建议的风险控制。
5. 平台支撑与可观测性：负责接入、执行、存储、调度、日志、审计和健康检查。

## 文档维护约定

1. 产品方向、阶段目标和模块划分写入 `docs/prd/`。
2. 单个业务模块的需求写入 `docs/prd/modules/`。
3. 开发可执行规格优先补充到 MVP、数据事件、验收和测试文档中。
4. 文档内链接统一使用相对路径，避免依赖本机绝对路径。
5. 如果删除旧文档，必须先确认其关键信息已迁移到当前 PRD 或归档目录。

## 当前仍需继续补充

1. 飞书开放平台权限清单和申请说明。
2. MCP Server 工具集配置规范。
3. Agent 审计日志格式规范。
4. API 接口清单和错误码。
5. 调度配置示例。
6. 飞书开放平台真实租户配置截图或操作手册。

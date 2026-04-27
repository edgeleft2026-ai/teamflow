---
name: overdue-task-reminder
trigger: task.overdue
condition: "days_overdue > 0"
action: notify
autonomy: auto
effectiveness: 0.85
triggered_count: 12
last_triggered: "2026-04-24T10:00:00"
created_at: "2026-01-15T09:00:00"
---

# 逾期任务提醒策略

当检测到任务逾期时，自动发送提醒消息给负责人和相关成员。

## 触发条件
- 任务状态非 done/cancelled
- 当前时间超过 deadline

## 执行动作
1. 查询逾期任务详情
2. 生成提醒消息（包含任务标题、逾期天数、负责人）
3. 推送飞书群/私聊

## 模板变量
- `{task_title}`: 任务标题
- `{assignee_name}`: 负责人姓名
- `{days_overdue}`: 逾期天数
- `{deadline}`: 截止日期

## 消息模板
⚠️ 任务逾期提醒
任务：{task_title}
负责人：{assignee_name}
已逾期 {days_overdue} 天（截止：{deadline}）
请尽快处理！

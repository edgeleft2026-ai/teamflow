---
name: member-overload-rebalance
trigger: task.member_overload
condition: "load_ratio > 2.0"
action: suggest_reassign
autonomy: approval
effectiveness: 0.6
triggered_count: 3
last_triggered: "2026-04-20T14:00:00"
created_at: "2026-03-01T10:00:00"
---

# 成员负载均衡策略

当检测到某成员任务负载过高时，建议重新分配任务。

## 触发条件
- 成员当前任务数 > 平均值 × 2
- 存在空闲成员可接收任务

## 执行动作
1. 识别过载成员和空闲成员
2. 生成任务重新分配建议
3. 需审批后执行

## 模板变量
- `{overloaded_member}`: 过载成员姓名
- `{load_ratio}`: 负载比率
- `{idle_members}`: 空闲成员列表
- `{suggested_moves}`: 建议迁移的任务

## 消息模板
📊 成员负载不均
{overloaded_member} 当前负载是平均值的 {load_ratio} 倍
建议将以下任务迁移给空闲成员：
{suggested_moves}

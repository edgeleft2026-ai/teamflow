# Gitea 权限同步模块 PRD

## 1. 模块目标

在 TeamFlow 已具备项目创建和飞书工作空间初始化能力的基础上，新增一条稳定、可维护的 Gitea 权限同步链路，使系统能够基于飞书项目群成员变化，自动完成 Gitea 仓库访问权限的开通和回收。

本模块的核心目标不是“给单个用户直接开仓库权限”，而是建立一套统一的权限模型：

```text
Feishu Group Member
  -> TeamFlow Project
  -> Gitea Team
  -> Gitea Repository Permission
```

即：

1. `Organization` 作为资源容器。
2. `Team` 作为权限组。
3. `Repository` 作为资源对象。
4. 用户通过加入 `Team` 间接获得 `Repository` 权限。

## 2. 模块边界

### 2.1 本模块负责

1. 在 `setup` 阶段拉取并选择默认 Gitea `Organization`。
2. 在项目创建阶段建立项目与 Gitea 权限资源的绑定关系。
3. 为项目创建或复用默认 Gitea `Team`。
4. 为项目创建或复用默认 Gitea `Repository`。
5. 将项目 `Team` 与项目 `Repository` 绑定读写权限。
6. 订阅飞书群成员进入和退出事件。
7. 将飞书用户身份映射到 Gitea 用户身份。
8. 在用户入群时自动加入 Gitea `Team`。
9. 在用户退群时自动从 Gitea `Team` 移除。
10. 将同步动作写入日志并提供可见失败反馈。
11. 保证授权链路幂等，避免重复开权和重复撤权。

### 2.2 本模块不负责

1. Gitea 自身的部署和安装。
2. 飞书登录接入 Gitea 的 OAuth 认证实现。
3. 复杂的多层组织架构同步。
4. 基于仓库目录、分支或代码所有者的细粒度授权。
5. 跨多个代码平台的统一权限编排。
6. 自动创建飞书群，飞书群初始化仍由 [飞书工作空间模块](./02-feishu-workspace.md) 负责。
7. 项目创建入口，项目创建入口仍由 [项目入口与初始化模块](./01-project-entry-and-onboarding.md) 负责。

## 3. 设计原则

1. 权限以 `Team` 为中心，不以 `Collaborator` 为中心。
2. 用户权限通过“加入 Team”继承，不直接散落在仓库上。
3. 先建立资源绑定，再处理成员同步。
4. 幂等优先，任何外部资源操作都必须可重复执行而不产生重复结果。
5. 单步失败不遮蔽已完成步骤，系统必须保留已成功的外部资源并报告失败原因。
6. 身份绑定显式优先，邮箱匹配仅作为辅助兜底。
7. 当前阶段默认一个项目至少有一个主 Team；是否扩展多 Team 由后续版本决定。

## 4. 核心概念

### 4.1 Gitea 权限模型

| 概念 | 说明 | 本模块作用 |
|---|---|---|
| Organization | 仓库与 Team 的容器 | 作为项目默认归属空间 |
| Team | 成员和仓库权限的组合 | 作为项目权限同步的核心对象 |
| Repository | 代码仓库 | 绑定到项目 Team |
| User | Gitea 账号 | 接收最终权限 |
| Collaborator | 单仓库直接协作者 | 仅作为过渡或补救方案，不作为长期主模型 |

### 4.2 飞书映射对象

| 概念 | 说明 |
|---|---|
| `open_id` | 飞书用户主身份 |
| `chat_id` | 飞书群主身份 |
| 项目群 | 项目协作的成员入口 |

### 4.3 TeamFlow 映射关系

推荐长期映射关系：

```text
Feishu Group(chat_id)
  -> Project
  -> Gitea Organization
  -> Gitea Team
  -> Gitea Repository
```

以及：

```text
Feishu User(open_id)
  -> UserIdentityBinding
  -> Gitea User(username / user_id)
```

## 5. 用户场景

### 5.1 Setup 选择默认 Organization

管理员首次运行 `teamflow setup`，系统验证 Gitea Token 后拉取可访问的组织列表，要求管理员选择默认 `Organization`，后续项目默认在该组织下创建仓库和 Team。

### 5.2 创建项目自动建立 Gitea 资源绑定

用户在飞书中创建项目后，系统自动在默认 `Organization` 下创建项目仓库、创建项目 Team，并将 Team 与仓库绑定读写权限。

### 5.3 用户进入项目群自动开通权限

项目成员被拉入飞书项目群后，系统收到飞书事件，根据 `chat_id` 找到项目，再根据 `open_id` 找到对应 Gitea 用户，将其加入项目 Team，从而自动获得仓库权限。

### 5.4 用户退出项目群自动回收权限

项目成员退出或被移出飞书项目群后，系统收到飞书事件，将该成员从项目 Team 中移除，仓库权限自动回收。

### 5.5 身份未绑定的失败提示

当成员进入群时，如果系统无法找到对应 Gitea 用户，不应阻断其他成员同步，而应记录失败、通知管理员并支持后续补绑定重试。

## 6. 输入输出

### 6.1 Setup 阶段输入输出

#### 输入

| 字段 | 来源 | 必填 | 说明 |
|---|---|---|---|
| `base_url` | 用户输入 | 是 | Gitea 地址 |
| `access_token` | 用户输入 | 是 | Gitea API Token |
| `default_private` | 用户输入 | 是 | 自动建仓库默认私有性 |
| `auto_create` | 用户输入 | 是 | 是否允许自动建仓库 |

#### 输出

| 字段 | 说明 |
|---|---|
| `org_name` | 默认 Gitea Organization |
| `gitea_user` | 当前 Token 对应用户信息 |
| `org_list` | 当前 Token 可见组织列表 |

### 6.2 项目创建阶段输入输出

#### 输入

| 字段 | 来源 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | 项目创建流程 | 是 | 项目唯一标识 |
| `project_name` | 项目创建流程 | 是 | 项目名称 |
| `git_repo_path` | 用户输入或自动生成 | 否 | 若为空且允许自动创建则自动建仓库 |
| `admin_open_id` | 项目创建流程 | 是 | 项目管理员 |
| `org_name` | setup 配置 | 是 | 默认组织 |

#### 输出

| 字段 | 说明 |
|---|---|
| `gitea_org_name` | 项目绑定组织 |
| `gitea_team_name` | 项目默认 Team |
| `git_repo_path` | 最终仓库路径 |
| `default_repo_permission` | 默认授予 Team 的仓库权限 |

### 6.3 入群同步阶段输入输出

#### 输入

| 字段 | 来源 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | 飞书事件 | 是 | 幂等去重 |
| `chat_id` | 飞书事件 | 是 | 项目群主标识 |
| `open_id` | 飞书事件 | 是 | 用户主标识 |
| `event_type` | 飞书事件 | 是 | `added` 或 `deleted` |

#### 输出

1. 权限同步成功或失败结果。
2. 成员是否成功加入或移出 Gitea Team。
3. 用户级动作日志。
4. 管理员可见失败提示。

## 7. 主流程设计

## 7.1 Setup 流程

```text
teamflow setup
  -> 输入 Gitea base_url / token
  -> check_token()
  -> 获取当前用户信息
  -> 获取可见 org 列表
  -> 用户选择默认 org_name
  -> 写入 config.yaml
```

业务要求：

1. 没有可见 `Organization` 时，允许降级为个人空间，但必须明确提示。
2. 只有当 `auto_create=true` 时，系统才允许项目创建时自动建仓库。
3. 若 Token 权限不足以读取组织列表，必须中断 setup 并明确报错。

## 7.2 项目创建阶段流程

推荐目标流程：

```text
项目创建完成
  -> 确定 project_id / project_name / admin_open_id
  -> 确定 gitea_org_name
  -> 创建或复用项目 Team
  -> 创建或复用项目 Repo
  -> 将 Team 绑定到 Repo 权限
  -> 写回项目访问绑定
  -> 发布后续事件
```

推荐顺序要求：

1. 先确定组织。
2. 再创建 Team。
3. 再创建 Repo。
4. 再绑定 Team 与 Repo 权限。

这样做的原因：

1. 先有 Team，后续成员入群时能立即同步。
2. 先有 Repo，再绑定权限时能得到明确结果。
3. 项目访问模型完整后，后续成员同步不需要再猜资源目标。

## 7.3 入群授权流程

```text
收到 im.chat.member.user.added_v1
  -> 幂等校验 event_id
  -> 根据 chat_id 找到 Project
  -> 根据 Project 找到 ProjectAccessBinding
  -> 根据 open_id 找到 UserIdentityBinding
  -> 将用户加入 Gitea Team
  -> 写入 ProjectMember
  -> 写入 ActionLog
```

## 7.4 退群回收流程

```text
收到 im.chat.member.user.deleted_v1
  -> 幂等校验 event_id
  -> 根据 chat_id 找到 Project
  -> 根据 Project 找到 ProjectAccessBinding
  -> 根据 open_id 找到 UserIdentityBinding
  -> 将用户移出 Gitea Team
  -> 更新 ProjectMember 状态
  -> 写入 ActionLog
```

## 8. 功能定义

### 8.1 默认 Organization 选择

要求：

1. setup 期间必须展示当前 Token 可见的组织列表。
2. 用户选择后将 `org_name` 固化到配置文件。
3. 后续自动创建仓库和 Team 默认都使用该 `org_name`。
4. 后续如支持项目级覆盖，可以允许项目创建时覆盖 `org_name`，但第一阶段默认使用全局值。

### 8.2 项目 Team 创建

要求：

1. 每个项目至少有一个默认 Team。
2. 默认 Team 推荐命名：

```text
{project_slug}-dev
```

3. Team 名称必须可重复计算，避免重试时生成不同名称。
4. Team 已存在时必须复用，不重复创建。

### 8.3 项目 Repo 创建

要求：

1. 若用户已提供 `git_repo_path`，应优先校验并绑定现有仓库。
2. 若未提供且 `auto_create=true`，系统自动创建 Repo。
3. 自动创建仓库时必须落在默认 `Organization` 下。
4. 仓库名建议使用项目 slug，避免空格和非法字符。

### 8.4 Team 与 Repo 权限绑定

要求：

1. 默认将项目 Team 绑定到项目 Repo。
2. 第一阶段默认权限为 `write`。
3. 如果绑定已存在，则视为成功，不重复创建。
4. 绑定失败必须写入日志并出现在创建回执中。

### 8.5 身份绑定

必须建立：

```text
Feishu open_id -> Gitea username / Gitea user_id
```

推荐规则：

1. 显式绑定优先。
2. 若显式绑定不存在，可尝试按邮箱匹配。
3. 邮箱匹配成功后，不应自动静默长期依赖，应回写绑定记录。
4. 仍无法匹配时，记录失败并通知管理员处理。

### 8.6 入群授权

要求：

1. 只要用户进入项目群，即触发授权同步。
2. 授权对象是 `Team`，不是直接授权仓库。
3. 同一个用户重复入群事件不得重复授权。
4. 某个用户授权失败时，不影响同批次其他用户。

### 8.7 退群回收

要求：

1. 用户退群或被移出群时应自动回收 Team 权限。
2. 同一个用户重复退群事件不得导致异常。
3. 如果用户已不在 Team 中，应视为幂等成功。

## 9. 数据模型要求

本模块建议新增以下数据对象。

### 9.1 UserIdentityBinding

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 主键 |
| `open_id` | string | 飞书用户标识 |
| `gitea_username` | string | Gitea 用户名 |
| `gitea_user_id` | string | Gitea 用户 ID |
| `email` | string | 用于辅助匹配 |
| `verified_at` | datetime | 绑定确认时间 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

约束：

1. `open_id` 唯一。
2. `gitea_username` 建议唯一。

### 9.2 ProjectAccessBinding

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 主键 |
| `project_id` | string | 项目标识 |
| `feishu_chat_id` | string | 项目群 ID |
| `gitea_org_name` | string | 绑定组织 |
| `gitea_team_name` | string | 绑定 Team |
| `git_repo_path` | string | 绑定仓库 |
| `default_repo_permission` | string | 默认仓库权限 |
| `enabled` | bool | 是否启用 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

约束：

1. `project_id` 唯一。
2. `feishu_chat_id` 在启用状态下唯一。

### 9.3 ProjectMember

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 主键 |
| `project_id` | string | 项目标识 |
| `open_id` | string | 飞书用户标识 |
| `display_name` | string | 成员显示名 |
| `role` | string | 成员角色 |
| `status` | string | active / removed / pending |
| `source` | string | feishu_group_sync / manual |
| `joined_at` | datetime | 加入时间 |
| `removed_at` | datetime | 移除时间 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

约束：

1. `project_id + open_id` 唯一。

## 10. 业务规则

1. `setup` 期间选定的默认 `org_name` 必须写入配置，不允许运行时无来源猜测。
2. 每个项目至少绑定一个 Gitea Team。
3. 项目默认 Team 必须在成员同步前准备完成。
4. Team 与 Repo 权限绑定失败时，项目创建可标记为部分成功，但必须发出明确告警。
5. 用户入群时只有在身份映射存在的情况下才执行授权。
6. 用户入群授权失败时，不得阻塞其他成员同步。
7. 用户退群时权限回收优先级高于状态展示，必须先做 Team 移除，再更新本地状态。
8. 所有外部调用都必须记录 `ActionLog`。
9. 所有事件消费都必须记录 `EventLog` 并使用幂等键。
10. 第一阶段默认一群对应一个主 Team，不处理一个群映射多个 Team 的复杂模型。

## 11. 外部能力要求

### 11.1 Gitea API 能力

模块至少需要以下能力：

1. `check_token()`
2. `list_orgs()`
3. `create_repo()`
4. `create_team()`
5. `get_team()` 或按名称查 Team
6. `add_team_repo()` 或绑定 Team 与 Repo
7. `add_team_member()`
8. `remove_team_member()`
9. `get_user()` / `search_user()`

### 11.2 飞书事件能力

模块至少需要订阅：

1. `im.chat.member.user.added_v1`
2. `im.chat.member.user.deleted_v1`

## 12. 执行策略

### 12.1 资源建立策略

项目创建阶段使用确定性编排优先，不建议把 Team / Repo / 权限绑定交给自由生成式 Agent 决策。原因：

1. 资源命名需要稳定。
2. 外部接口失败后需要明确补偿。
3. 权限动作属于高确定性动作。

### 12.2 成员同步策略

成员同步建议采用事件驱动主链路：

```text
成员进群/退群事件
  -> 立即同步 Team 成员
```

后续可追加定时对账任务作为补偿：

```text
定时扫描群成员
  -> 对比 Team 成员
  -> 修复差异
```

第一阶段不要求必须实现全量对账，但应预留扩展点。

## 13. 异常处理

| 异常 | 处理要求 |
|---|---|
| Token 校验失败 | setup 中断，明确提示无法连接 Gitea |
| 无法获取组织列表 | setup 中断，提示权限不足或配置错误 |
| Team 创建失败 | 项目创建标记部分失败，停止后续成员同步准备 |
| Repo 创建失败 | 项目创建失败或部分失败，不写入错误仓库绑定 |
| Team 绑定 Repo 失败 | 记录失败并告警，不得伪装成功 |
| chat_id 找不到项目 | 丢弃事件并记录告警 |
| open_id 无身份映射 | 跳过该成员，通知管理员补绑定 |
| add_team_member 失败 | 记录失败，允许后续重试 |
| remove_team_member 失败 | 记录失败，标记待补偿 |
| 重复事件投递 | 幂等成功，不重复操作 |

## 14. 成功指标

1. setup 阶段组织拉取成功率。
2. 项目创建阶段 Team 创建成功率。
3. 项目创建阶段 Repo 创建成功率。
4. Team 与 Repo 绑定成功率。
5. 成员入群授权成功率。
6. 成员退群回收成功率。
7. 身份未绑定导致的失败占比。
8. 重复事件导致的重复授权次数。

建议第一阶段目标：

1. 正常配置下项目 Team 创建成功率达到 95%。
2. Team 与 Repo 绑定成功率达到 95%。
3. 成员进群授权链路成功率达到 90% 以上。
4. 重复事件导致重复授权次数为 0。

## 15. 验收标准

1. `teamflow setup` 能拉取并展示 Gitea 组织列表。
2. 管理员能在 setup 期间选择默认 `Organization` 并写入配置。
3. 创建项目时系统能在默认 `Organization` 下创建或复用项目 Team。
4. 创建项目时系统能在默认 `Organization` 下创建或复用项目 Repo。
5. 系统能将项目 Team 绑定到项目 Repo 的 `write` 权限。
6. 项目访问绑定信息能成功写入数据库。
7. 系统能成功订阅并接收飞书成员进群和退群事件。
8. 成员进群后，若存在身份绑定，系统能将其加入项目 Team。
9. 成员加入 Team 后可以自然获得项目 Repo 权限。
10. 成员退群后，系统能将其从 Team 移除。
11. 身份绑定缺失时，系统不会中断整批处理，并能产生明确失败记录。
12. 重复消费同一成员变更事件不会重复加权或重复撤权。
13. 所有外部动作都能在日志中按项目和成员维度追踪。

## 16. 分阶段交付建议

### 16.1 Phase 1：可用版

交付目标：

1. setup 支持选择默认 `Organization`。
2. 创建项目时自动创建 Team、Repo 和 Team-Repo 权限绑定。
3. 新增成员进群授权和退群撤权事件处理。
4. 引入最基础的身份绑定表。

### 16.2 Phase 2：增强版

交付目标：

1. 支持一个项目多个 Team，例如 `dev` / `readonly`。
2. 支持邮箱自动匹配和绑定确认。
3. 增加定时对账任务。
4. 增加管理员可见的失败处理入口和手动重试能力。

## 17. 与现有模块关系

1. 项目创建触发和基础信息采集由 [项目入口与初始化模块](./01-project-entry-and-onboarding.md) 提供。
2. 飞书群和项目文档初始化由 [飞书工作空间模块](./02-feishu-workspace.md) 提供。
3. 本模块在二者之间补上 Gitea 权限模型和成员同步能力，形成完整闭环：

```text
创建项目
  -> 建立飞书工作空间
  -> 建立 Gitea 权限资源
  -> 成员入群即同步权限
```

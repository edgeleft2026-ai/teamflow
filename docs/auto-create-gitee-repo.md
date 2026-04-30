# 自动创建 Gitee 仓库方案

## 1. 背景

当前项目创建流程中，用户需要手动输入 Git 仓库地址来关联已有仓库。这在实际使用中存在以下问题：

1. 用户可能还没有创建仓库，需要先去 Gitee/GitHub 手动创建再回来填写
2. 仓库地址容易填错，导致后续工作空间初始化引用错误的仓库
3. 增加了创建项目的交互步骤和认知负担

**目标**：将"手动关联仓库"改为"自动创建仓库并授权"，同时保留手动关联已有仓库的选项。

## 2. 需求确认

| 项目 | 决策 |
|------|------|
| Git 平台 | Gitee（码云） |
| 授权范围 | 仅项目管理员（写权限） |
| 输入方式 | 仓库地址改为可选；填了关联已有，不填自动创建 |

## 3. 现状分析

### 3.1 当前流程

**文本对话式**：

```
用户: 开始创建项目
系统: 请输入项目名称
用户: TeamFlow
系统: 请输入 Git 仓库地址或本地路径    ← 必填，手动输入
用户: https://gitee.com/org/repo.git
系统: 创建成功
```

**卡片表单式**：

- 表单有两个必填字段：`project_name`（项目名称）、`git_repo_path`（仓库地址）
- 提交后 Worker 执行：创建记录 → 发布事件 → （下游）初始化工作空间

### 3.2 涉及 git_repo_path 的代码位置

| 文件 | 位置 | 说明 |
|------|------|------|
| `storage/models.py` | `Project` / `ProjectFormSubmission` | `git_repo_path: str` 必填字段 |
| `storage/repository.py` | `ProjectRepo.create()` | 入参 `git_repo_path` |
| `storage/repository.py` | `ProjectFormSubmissionRepo.create()` | 入参 `git_repo_path` |
| `orchestration/project_flow.py` | `_handle_collect_name()` | 提示"请输入 Git 仓库地址" |
| `orchestration/project_flow.py` | `_handle_collect_repo()` | 收集用户输入的仓库地址 |
| `orchestration/project_flow.py` | `submit_form()` | 表单校验 `git_repo_path` 必填 |
| `orchestration/project_flow.py` | `_process_submission()` | Worker 执行创建流程 |
| `orchestration/card_templates.py` | `project_create_form_card()` | 表单中的仓库地址输入框 |
| `orchestration/workspace_flow.py` | `WorkspaceInitFlow` | 把 `git_repo_path` 传给 Agent |
| `ai/prompts.py` | `WORKSPACE_INIT_PROMPT` | 文档内容中引用仓库地址 |

## 4. 改造方案

### 4.1 新增 Gitee 配置

**`config/settings.py`** 新增 `GiteeConfig`：

```python
class GiteeConfig(BaseModel):
    access_token: str = ""          # Gitee 个人访问令牌
    base_url: str = "https://gitee.com/api/v5"
    default_private: bool = True    # 默认创建私有仓库
    auto_create: bool = True        # 是否启用自动创建仓库

class TeamFlowConfig(BaseModel):
    feishu: FeishuConfig
    agent: AgentConfig = AgentConfig()
    gitee: GiteeConfig = GiteeConfig()  # 新增
```

**`config.example.yaml`** 新增：

```yaml
gitee:
  access_token: ""              # Gitee 个人访问令牌（https://gitee.com/profile/personal_access_tokens）
  base_url: "https://gitee.com/api/v5"
  default_private: true         # 默认创建私有仓库
  auto_create: true             # 启用自动创建仓库
```

### 4.2 新增 Gitee 服务模块

新建 `src/teamflow/git/__init__.py` 和 `src/teamflow/git/gitee_service.py`：

```python
class GiteeService:
    """封装 Gitee API：创建仓库、添加协作者"""

    def __init__(self, config: GiteeConfig) -> None: ...

    async def create_repo(self, name: str, *, private: bool = True, description: str = "") -> RepoResult:
        """
        POST https://gitee.com/api/v5/user/repos
        参数: access_token, name, description, private, has_issues, has_wiki, auto_init
        返回: RepoResult(full_name, html_url, ssh_url, https_url)
        """

    async def add_collaborator(self, repo_full_name: str, username: str, permission: str = "push") -> None:
        """
        PUT https://gitee.com/api/v5/repos/{owner}/{repo}/collaborators/{username}
        参数: access_token, permission (admin/push/pull)
        """

    async def get_current_user(self) -> UserInfo:
        """
        GET https://gitee.com/api/v5/user
        用于验证 token 有效性
        """
```

**关键 API 说明**：

| 操作 | 方法 | 端点 | 核心参数 |
|------|------|------|----------|
| 创建仓库 | POST | `/user/repos` | `access_token`, `name`, `private`, `auto_init`, `description` |
| 添加协作者 | PUT | `/repos/{owner}/{repo}/collaborators/{username}` | `access_token`, `permission` |
| 获取当前用户 | GET | `/user` | `access_token` |

**注意事项**：
- Gitee 添加协作者需要 **用户名（username）**，不是 open_id。需要通过飞书通讯录查询用户的 Gitee 用户名，或者在项目创建时让用户输入
- `auto_init=true` 可以在创建仓库时自动初始化 README，避免空仓库

### 4.3 数据模型变更

**`storage/models.py`**：

```python
class Project(SQLModel, table=True):
    # ... 其他字段不变
    git_repo_path: str | None = Field(default=None)  # 从必填改为可选
    # 新增字段
    git_repo_platform: str | None = Field(default=None)  # "gitee" | "github" | "manual"
    git_repo_auto_created: bool = Field(default=False)   # 是否自动创建

class ProjectFormSubmission(SQLModel, table=True):
    # ... 其他字段不变
    git_repo_path: str | None = Field(default=None)  # 从必填改为可选
```

**数据库迁移**：`git_repo_path` 从 `NOT NULL` 变为 `NULLABLE`，需要迁移脚本处理已有数据。

### 4.4 项目创建流程变更

#### 4.4.1 文本对话式

**改造前**：

```
collecting_project_name → collecting_repo → creating_project → created
```

**改造后**：

```
collecting_project_name → (可选)collecting_repo → creating_project → created
```

具体变化：
1. 收集完项目名称后，提示改为：

   ```
   项目名称：{name}

   请输入 Git 仓库地址（留空则自动在 Gitee 创建）：
   ```

2. 用户输入为空时，跳过收集仓库步骤，进入自动创建流程
3. `_create_project()` 中：
   - 如果 `git_repo_path` 为空且 `gitee.auto_create=True`，调用 Gitee API 创建仓库
   - 创建成功后，将返回的仓库地址写入 `git_repo_path`
   - 创建失败时，项目记录仍创建，但标记仓库创建失败

#### 4.4.2 卡片表单式

**表单变更**：

- `git_repo_path` 输入框：从必填 `*` 改为可选，placeholder 改为 "留空则自动在 Gitee 创建"

**提交校验变更**：

```python
# 改造前
if not project_name or not git_repo_path:
    return CardActionHandleResult(toast_type="error", toast_text="请先填写项目名称和仓库地址")

# 改造后
if not project_name:
    return CardActionHandleResult(toast_type="error", toast_text="请先填写项目名称")
```

#### 4.4.3 Worker 执行步骤变更

**新增步骤**：在"创建项目记录"和"发布项目事件"之间插入"创建代码仓库"步骤。

```
表单已提交
→ 创建项目记录
→ 创建代码仓库          ← 新增（仅当 git_repo_path 为空时执行）
→ 发布项目事件
→ 创建项目群
→ ...
```

**`_process_submission()` 伪代码**：

```python
# 1. 创建项目记录（git_repo_path 可能为空）
project = self.project_repo.create(
    name=submission.project_name,
    git_repo_path=submission.git_repo_path or "",
    admin_open_id=submission.open_id,
)

# 2. 如果没有仓库地址，自动创建
if not submission.git_repo_path and self.gitee_config.auto_create:
    self._mark_step(steps, STEP_CREATE_REPO, status="running", detail="正在 Gitee 创建仓库")
    result = await self.gitee_service.create_repo(
        name=submission.project_name,
        private=self.gitee_config.default_private,
    )
    # 更新项目记录
    project.git_repo_path = result.https_url
    project.git_repo_platform = "gitee"
    project.git_repo_auto_created = True
    self._mark_step(steps, STEP_CREATE_REPO, status="success", detail=f"仓库已创建: {result.html_url}")

    # 授权项目管理员
    if admin_gitee_username:
        await self.gitee_service.add_collaborator(result.full_name, admin_gitee_username, permission="push")
elif submission.git_repo_path:
    self._mark_step(steps, STEP_CREATE_REPO, status="skipped", detail="使用已有仓库")
else:
    self._mark_step(steps, STEP_CREATE_REPO, status="skipped", detail="未配置 Gitee，跳过自动创建")

# 3. 发布事件（后续流程不变）
```

### 4.5 卡片模板变更

**`project_create_form_card()`**：

```python
# 改造前
{
    "tag": "input",
    "name": "git_repo_path",
    "placeholder": {"tag": "plain_text", "content": "例如：https://github.com/org/repo.git"},
    "label": {"tag": "plain_text", "content": "仓库地址 *"},
}

# 改造后
{
    "tag": "input",
    "name": "git_repo_path",
    "placeholder": {"tag": "plain_text", "content": "留空则自动在 Gitee 创建仓库"},
    "label": {"tag": "plain_text", "content": "仓库地址（可选）"},
}
```

**`project_create_status_card()`**：

- 仓库地址显示区域增加判断：如果为空，显示"自动创建中"或"未关联仓库"

**`project_created_card()`**：

- 仓库地址显示增加判断：区分"已关联"和"自动创建"

### 4.6 工作空间初始化适配

**`workspace_flow.py`** 和 **`ai/prompts.py`**：

- `git_repo_path` 可能为空，Agent 创建文档时需要判断
- 如果有仓库地址，文档中包含仓库信息；如果没有，文档中标注"暂未关联代码仓库"

## 5. 管理员 Gitee 用户名获取方案

Gitee 添加协作者需要 **username**，而非飞书 open_id。有以下方案：

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 用户首次使用时绑定 Gitee 用户名 | 一次绑定，后续自动 | 需要额外的绑定流程 |
| B. 项目创建时让用户输入 Gitee 用户名 | 简单直接 | 每次都要输入 |
| C. 在飞书通讯录自定义字段中存储 | 自动化程度高 | 需要企业管理员配置 |
| D. 仅创建仓库，不自动授权 | 最简单 | 管理员需手动授权 |

**推荐方案 A**：在用户首次触发项目创建时，如果检测到未绑定 Gitee 用户名，引导用户输入并持久化存储（新增 `UserGiteeBinding` 模型）。后续创建项目时自动使用。

```python
class UserGiteeBinding(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    open_id: str = Field(index=True, unique=True)
    gitee_username: str
    created_at: datetime = Field(default_factory=_utcnow)
```

## 6. 异常处理

| 异常场景 | 处理方式 |
|----------|----------|
| Gitee token 无效 | 启动时自检，项目创建时返回明确错误提示 |
| 仓库名已存在 | 自动添加后缀（如 `-2`），或提示用户手动指定 |
| 仓库创建超时 | 标记步骤失败，项目仍创建，用户可后续手动关联 |
| 添加协作者失败 | 仓库已创建，但管理员需手动在 Gitee 添加成员 |
| Gitee API 限流 | 记录日志，返回"仓库创建服务暂时不可用"提示 |
| 用户未绑定 Gitee 用户名 | 跳过授权步骤，仅创建仓库，提示用户后续绑定 |

## 7. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/teamflow/git/__init__.py` | 新增 | 模块初始化 |
| `src/teamflow/git/gitee_service.py` | 新增 | Gitee API 封装 |
| `src/teamflow/config/settings.py` | 修改 | 新增 `GiteeConfig` |
| `config.example.yaml` | 修改 | 新增 `gitee` 配置段 |
| `src/teamflow/storage/models.py` | 修改 | `git_repo_path` 改可选，新增字段 |
| `src/teamflow/storage/repository.py` | 修改 | 适配可选 `git_repo_path` |
| `src/teamflow/orchestration/project_flow.py` | 修改 | 流程改造 + 自动创建仓库步骤 |
| `src/teamflow/orchestration/card_templates.py` | 修改 | 表单和状态卡片改造 |
| `src/teamflow/orchestration/workspace_flow.py` | 修改 | 适配 `git_repo_path` 可为空 |
| `src/teamflow/ai/prompts.py` | 修改 | 适配 `git_repo_path` 可为空 |
| `src/teamflow/main.py` | 修改 | 初始化 `GiteeService` |

## 8. 实施优先级

1. **P0**：Gitee 配置 + 服务模块 + 数据模型变更
2. **P0**：卡片表单式流程改造（主要入口）
3. **P1**：文本对话式流程改造
4. **P1**：管理员 Gitee 用户名绑定
5. **P2**：工作空间初始化适配
6. **P2**：启动自检（Gitee token 有效性验证）

# TeamFlow Gitea 项目与入群授权流程图

## 1. 一图看懂

```text
Feishu User(open_id)        Feishu Group(chat_id)
        |                           |
        v                           v
   TeamFlow Project  <---------  feishu_group_id
        |
        +------ git_repo_path ------> Gitea Repo
        |
        +------ admin_open_id ------> Feishu Admin
        |
        +------ feishu_doc_url -----> Feishu Doc
```

## 2. Gitea 概念图

```text
Gitea Organization
  |
  +-- Team A -------------------+
  |    |                        |
  |    +-- User 1               +--> Repo X (write)
  |    +-- User 2               +--> Repo Y (write)
  |
  +-- Team B -------------------+
       |                        |
       +-- User 3               +--> Repo X (read)
       +-- User 4
```

```text
Organization = 容器
Team         = 权限组
Repo         = 仓库
User         = 用户
```

## 3. 当前代码已实现

```text
teamflow setup
  -> 生成 config.yaml
teamflow run
  -> 启动事件订阅
用户创建项目
  -> Project 落库
  -> 可选自动创建 Gitea Repo
  -> 发布 project.created
  -> 初始化飞书群 / 文档
  -> 回写 Project
```

## 4. 当前代码未实现

```text
用户进飞书项目群
  -> 识别 chat_id
  -> 找到 Project
  -> 找到 Gitea User
  -> 自动加 Team / Repo 权限
```

## 5. Setup 流程图

```text
teamflow setup
  |
  +-- 检查 lark-cli
  |
  +-- 配置 Feishu
  |     +-- 扫码自动注册
  |     \-- 手动输入 app_id/app_secret
  |
  +-- 配置 LLM
  |
  +-- 配置 Gitea
  |     +-- base_url
  |     +-- access_token
  |     +-- default_private
  |     +-- auto_create
  |     \-- org_name
  |
  \-- 写入 config.yaml
```

## 6. 配置结果图

```yaml
feishu:
  app_id: "..."
  app_secret: "..."
  brand: "feishu"
  admin_open_id: "..."

gitea:
  base_url: "https://your-gitea.example.com"
  access_token: "..."
  default_private: true
  auto_create: true
  org_name: "your-org"
```

```text
org_name
  -> 决定自动创建的仓库默认落到哪个 Organization
```

## 7. 启动流程图

```text
teamflow run
  -> 读 config.yaml
  -> init_db()
  -> 启动 lark-cli event +subscribe
  -> 初始化 Agent / ToolProvider
  -> 注册 project.created 处理器
  -> 监听事件目录
```

## 8. 当前订阅事件

```text
已实现:
  - im.message.receive_v1
  - card.action.trigger

未实现:
  - im.chat.member.user.added_v1
  - im.chat.member.user.deleted_v1
```

## 9. 项目创建绑定流程图

```text
用户提交项目表单
  -> ProjectFormSubmission
  -> worker 线程
  -> 创建 Project
  -> 如果 git_repo_path 为空 且 auto_create=true
       -> Gitea create_repo(name, org=org_name)
  -> 发布 project.created
```

## 10. 当前 Project 绑定图

```text
Project
  +-- name
  +-- git_repo_path
  +-- admin_open_id
  +-- feishu_group_id
  +-- feishu_group_link
  +-- feishu_doc_url
  +-- git_repo_platform
  \-- git_repo_auto_created
```

## 11. 工作空间初始化图

```text
project.created
  -> 创建飞书项目群
  -> 拉项目管理员入群
  -> 获取群链接
  -> 创建项目文档
  -> 转交文档权限
  -> 回写 Project
  -> 发布 project.workspace_initialized
  -> 发送欢迎消息
```

## 12. 当前绑定闭环

```text
Feishu Admin(open_id)
  -> Project.admin_open_id

Project
  -> Gitea Repo(git_repo_path)
  -> Feishu Group(feishu_group_id)
  -> Feishu Doc(feishu_doc_url)

config.gitea.org_name
  -> Gitea Organization
```

## 13. 推荐的长期模型

```text
Feishu Group(chat_id)
  -> TeamFlow Project
  -> Gitea Organization
  -> Gitea Team
  -> Gitea Repo(一个或多个)
```

```text
不要长期用:
  群成员 -> 直接加 Repo Collaborator

推荐长期用:
  群成员 -> 加 Gitea Team
  Team    -> 控制 Repo 权限
```

## 14. 入群即授权目标流程图

```text
用户进入飞书项目群
  -> 收到 added_v1 事件
  -> 根据 chat_id 找到 Project
  -> 根据 Project 找到 Gitea Team
  -> 根据 open_id 找到 Gitea User
  -> 把用户加入 Gitea Team
  -> Team 自动获得 Repo 权限
```

## 15. 退群回收权限流程图

```text
用户退出飞书项目群
  -> 收到 deleted_v1 事件
  -> 根据 chat_id 找到 Project
  -> 找到 Gitea Team
  -> 从 Team 移除用户
  -> 权限自动回收
```

## 16. 需要补的三层绑定

```text
1. 身份绑定
   Feishu open_id -> Gitea username/user_id

2. 项目绑定
   Project -> chat_id -> gitea_team_name

3. 成员绑定
   Project + open_id -> ProjectMember
```

## 17. 推荐新增表

```text
UserIdentityBinding
  - open_id
  - gitea_username
  - gitea_user_id
  - email

ProjectAccessBinding
  - project_id
  - feishu_chat_id
  - gitea_org_name
  - gitea_team_name
  - default_repo_permission

ProjectMember
  - project_id
  - open_id
  - role
  - status
  - source
```

## 18. 两种实现路线

### 18.1 MVP 快速版

```text
进群事件
  -> 找 Project
  -> 找 Gitea 用户
  -> add_collaborator(repo, user)
```

### 18.2 推荐长期版

```text
进群事件
  -> 找 Project
  -> 找 Team
  -> 找 Gitea 用户
  -> add_team_member(team, user)
```

## 19. 最终推荐端到端图

```text
teamflow setup
  -> 选择 org_name = teamflow

用户创建项目
  -> 创建 Project
  -> 自动创建 Repo
  -> 初始化 Feishu Group / Doc
  -> 建立 ProjectAccessBinding
       chat_id -> project-a-dev team

用户被拉入项目群
  -> added_v1
  -> open_id -> gitea_username
  -> 加入 project-a-dev
  -> 自动获得 project-a repo 权限
```

## 20. 结论

```text
当前已完成:
  Project <- admin_open_id / git_repo_path / feishu_group_id / feishu_doc_url

当前未完成:
  chat_id -> project
  project -> gitea_team
  open_id -> gitea_user
  入群/退群 -> team 权限同步

最终推荐:
  飞书群成员同步 -> Gitea Team 成员同步 -> Team 控制 Repo 权限
```

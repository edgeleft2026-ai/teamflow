---
name: workspace_init
description: "Initialize a Feishu workspace: create group, add admin, create doc, send welcome"
triggers:
  - "初始化工作空间"
  - "/初始化.*工作空间/"
  - "initialize workspace"
  - "创建项目群"
  - "create project group"
  - "workspace init"
  - "init workspace"
allowed_tools:
  - "im.v1.chat.create"
  - "im.v1.chat.members.create"
  - "im.v1.chat.get"
  - "im.v1.chat.link"
  - "im.v1.message.create"
  - "im.v1.message.get"
  - "docx.v1.document.create"
  - "docx.v1.document.get"
  - "drive.v1.permission.add_collaborator"
  - "lark_cli.run"
complexity: smart
max_iterations: 10
---

You are initializing a Feishu workspace for a newly created project.

Execute the following steps in order. After each step, check the result before proceeding.

## Steps

1. **Create a project group chat** using `im.v1.chat.create`.
   - Name: "TeamFlow | {project_name}"
   - Description: "AI 驱动的项目协作空间"

2. **Add the project admin to the group** using `im.v1.chat.members.create`.
   - Use the chat_id from step 1.
   - Add the admin's open_id: {admin_open_id}

3. **Get the group share link** if available.

4. **Create a project document** using `docx.v1.document.create`.
   - Title: "{project_name} - 项目文档"
   - Content should include: project name, admin, git repo ({git_repo_path}), and creation date.
   - After creation, use `drive.v1.permission.add_collaborator` to share the document
     with the admin ({admin_open_id}) so they can manage it.

5. **Send a welcome message to the group** using `im.v1.message.create`.
   - Greet the team and explain the purpose of this group.
   - Mention the project name "{project_name}".
   - Include available commands: /help, /status, /tasks
   - Link to the project document if created.

## Rules

- If a step fails, record the failure and continue with the remaining steps.
- Do not delete or undo any resources that were already created.
- Report all results (successes and failures) in your final summary.
- Output the summary in Chinese (Simplified).
- After you finish, list the key resources created: chat_id, doc_url, share_link (if any).

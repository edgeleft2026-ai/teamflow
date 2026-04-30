"""System prompts for different Agent task types."""

# Workspace initialization prompt for M2.
# The agent creates a Feishu group, adds the admin, creates a doc, and sends a welcome message.
WORKSPACE_INIT_PROMPT = """\
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
"""


def get_system_prompt(agent_type: str) -> str:
    """Return the system prompt for a given agent type.

    Args:
        agent_type: One of "workspace_init" (currently the only type).

    Returns:
        The system prompt string.
    """
    prompts = {
        "workspace_init": WORKSPACE_INIT_PROMPT,
    }
    return prompts.get(agent_type, "")

from __future__ import annotations

import uuid


def startup_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "TeamFlow 已就绪"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**启动完成**\n"
                        "机器人已连接飞书并进入可用状态，可以开始创建和管理项目。"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "column_set",
                "flex_mode": "trisect",
                "background_style": "grey",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**连接状态**\n已连接飞书",
                                },
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**运行模式**\n运行中",
                                },
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**下一步**\n开始创建项目",
                                },
                            }
                        ],
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**推荐操作**\n"
                        '发送 **"开始创建项目"**，即可进入表单填写并开始创建流程。'
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "后续你会在同一张卡片中看到项目创建、工作空间初始化和结果反馈。",
                },
            },
        ],
    }


def welcome_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "TeamFlow"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**AI 项目协作助手**\n"
                        "帮助你完成项目创建、工作空间初始化和后续协作管理。"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "column_set",
                "flex_mode": "bisect",
                "background_style": "default",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "top",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": (
                                        "**开始创建**\n"
                                        "发送 **开始创建项目**\n"
                                        "快速发起一个新项目"
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "vertical_align": "top",
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": (
                                        "**后续能力**\n"
                                        "/status、/tasks\n"
                                        "更多能力持续开放中"
                                    ),
                                },
                            }
                        ],
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**推荐操作**\n"
                        "1. 发送 **开始创建项目**\n"
                        "2. 填写项目名和仓库地址\n"
                        "3. 在同一张卡片里查看创建与初始化进度"
                    ),
                },
            },
        ],
    }


def project_created_card(project_id: str, name: str, repo: str | None) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "项目创建成功"},
            "template": "green",
        },
        "elements": [
            {
                "tag": "column_set",
                "flex_mode": "bisect",
                "background_style": "grey",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {"tag": "lark_md", "content": f"**项目名**\n{name}"},
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**项目 ID**\n{project_id[:8]}",
                                },
                            }
                        ],
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**仓库**: {repo}" if repo else "**仓库**: 自动创建中"},
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "工作空间初始化中，将自动创建项目群和文档，完成后通知您。",
                },
            },
        ],
    }


def project_create_form_card(request_id: str | None = None) -> dict:
    """Interactive card with a form for project creation (JSON 2.0)."""
    current_request_id = request_id or str(uuid.uuid4())
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "创建项目"},
            "template": "blue",
        },
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**填写后将立即开始创建**\n"
                            "提交后，这张卡会直接切换为进度卡，并持续显示后续初始化状态。"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "form",
                    "name": "project_create_form",
                    "elements": [
                        {
                            "tag": "input",
                            "name": "project_name",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "例如：TeamFlow、数据中台、增长实验室",
                            },
                            "label": {
                                "tag": "plain_text",
                                "content": "项目名称 *",
                            },
                        },
                        {
                            "tag": "input",
                            "name": "git_repo_path",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "留空则自动在 Gitea 创建仓库",
                            },
                            "label": {
                                "tag": "plain_text",
                                "content": "仓库地址（可选）",
                            },
                        },
                        {
                            "tag": "column_set",
                            "flex_mode": "none",
                            "columns": [
                                {
                                    "tag": "column",
                                    "width": "auto",
                                    "elements": [
                                        {
                                            "tag": "button",
                                            "text": {
                                                "tag": "plain_text",
                                                "content": "开始创建",
                                            },
                                            "type": "primary",
                                            "action_type": "form_submit",
                                            "name": "btn_submit",
                                            "value": {
                                                "teamflow_action": "submit_project_form",
                                                "request_id": current_request_id,
                                            },
                                        },
                                    ],
                                },
                                {
                                    "tag": "column",
                                    "width": "auto",
                                    "elements": [
                                        {
                                            "tag": "button",
                                            "text": {
                                                "tag": "plain_text",
                                                "content": "清空重填",
                                            },
                                            "type": "default",
                                            "action_type": "form_reset",
                                            "name": "btn_reset",
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**提交后你会看到**\n"
                            "项目创建、工作空间初始化、欢迎消息发送等关键步骤。\n"
                            "如需取消，直接忽略这张卡即可。"
                        ),
                    },
                },
            ],
        },
    }


def project_create_status_card(
    *,
    status: str,
    project_name: str,
    git_repo_path: str | None,
    steps: list[dict],
    current_step: str,
    project_id: str | None = None,
    error_message: str | None = None,
) -> dict:
    is_workspace_stage = (
        "工作空间" in current_step
        or "项目群" in current_step
        or "管理员入群" in current_step
        or "群链接" in current_step
        or "项目文档" in current_step
        or "文档所有权" in current_step
        or "欢迎消息" in current_step
    )
    header_title = "创建项目中"
    header_template = "blue"
    summary = "已接收创建请求，正在执行。"

    if status == "running" and is_workspace_stage:
        header_title = "工作空间初始化中"
        summary = "项目记录已创建，正在继续完成项目群、文档、归属和欢迎消息。"
    elif status == "succeeded" and is_workspace_stage:
        header_title = "项目与工作空间已就绪"
        header_template = "green"
        summary = "项目创建、工作空间初始化和欢迎消息均已完成。"
    elif status == "succeeded":
        header_title = "项目与工作空间已就绪"
        header_template = "green"
        summary = "项目创建、工作空间初始化和欢迎消息均已完成。"
    elif status == "partial_failed":
        header_title = "项目已创建，初始化部分完成"
        header_template = "orange"
        summary = error_message or "项目已创建成功，但部分工作空间步骤未完成。"
    elif status == "failed" and project_id:
        header_title = "工作空间初始化失败"
        header_template = "red"
        summary = error_message or "项目已创建，但工作空间初始化失败。"
    elif status == "failed":
        header_title = "项目创建失败"
        header_template = "red"
        summary = error_message or "创建过程中发生异常，请重新发起。"

    total_steps = len(steps)
    completed_steps = sum(1 for step in steps if step.get("status") == "success")
    failed_steps = sum(1 for step in steps if step.get("status") == "failure")

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**状态说明**\n{summary}\n\n"
                    f"**当前步骤**: {current_step}"
                ),
            },
        },
        {"tag": "hr"},
        {
            "tag": "column_set",
            "flex_mode": "bisect",
            "background_style": "grey",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "div",
                            "text": {"tag": "lark_md", "content": f"**项目名**\n{project_name}"},
                        }
                    ],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    f"**标识**\n{project_id[:8]}"
                                    if project_id
                                    else "**标识**\n待生成"
                                ),
                            },
                        }
                    ],
                },
            ],
        },
        {
            "tag": "column_set",
            "flex_mode": "trisect",
            "background_style": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**总步骤**\n{total_steps}",
                            },
                        }
                    ],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**已完成**\n{completed_steps}",
                            },
                        }
                    ],
                },
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**异常**\n{failed_steps}",
                            },
                        }
                    ],
                },
            ],
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**仓库地址**\n{git_repo_path}" if git_repo_path else "**仓库地址**\n将自动在 Gitea 创建",
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "**执行进度**"},
        },
    ]

    for step in steps:
        step_status = step.get("status", "pending")
        icon = _project_step_icon(step_status)
        detail = step.get("detail", "")
        content = f"{icon} **{step['name']}**"
        if detail:
            content = f"{content}\n{detail}"
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": content},
            }
        )
        if step is not steps[-1]:
            elements.append({"tag": "hr"})

    if status in {"failed", "partial_failed"}:
        elements.extend(
            [
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**下一步建议**\n请检查上方失败步骤。"
                            if project_id
                            else '**下一步建议**\n请重新发送 **"开始创建项目"** 再次发起。'
                        ),
                    },
                },
            ]
        )

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": header_template,
        },
        "body": {
            "direction": "vertical",
            "elements": elements,
        },
    }


def project_failed_card(step: str, reason: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "创建未完成"},
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "本次创建没有成功完成，你可以根据下方信息快速定位问题。",
                },
            },
            {"tag": "hr"},
            {
                "tag": "column_set",
                "flex_mode": "bisect",
                "background_style": "default",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {"tag": "lark_md", "content": f"**失败步骤**\n{step}"},
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {"tag": "lark_md", "content": f"**原因**\n{reason}"},
                            }
                        ],
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**下一步建议**\n"
                        '修正问题后，重新发送 **"开始创建项目"** 再试一次。'
                    ),
                },
            },
        ],
    }


def _project_step_icon(status: str) -> str:
    if status == "success":
        return "✅"
    if status == "running":
        return "⏳"
    if status == "failure":
        return "❌"
    if status == "skipped":
        return "⏭️"
    return "⬜"


def workspace_init_result_card(project_name: str, steps: list[dict]) -> dict:
    """Build a card showing workspace initialization step results.

    steps: list of {"name": str, "status": "success"|"failure"|"skipped", "detail": str}
    """
    elements: list[dict] = []
    for step in steps:
        status = step.get("status", "unknown")
        detail = step.get("detail", "")
        if status == "success":
            icon = "✅"
        elif status == "failure":
            icon = "❌"
        elif status == "skipped":
            icon = "⏭️"
        else:
            icon = "❓"

        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{icon} **{step['name']}**\n{detail}",
                },
            }
        )
        elements.append({"tag": "hr"})

    # Remove trailing hr
    if elements and elements[-1]["tag"] == "hr":
        elements.pop()

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"工作空间初始化结果 | {project_name}"},
            "template": "blue",
        },
        "elements": elements,
    }


def workspace_welcome_card(project_name: str, doc_url: str | None = None) -> dict:
    """Welcome card sent to the newly created project group."""
    doc_line = f"\n📄 [项目文档]({doc_url})" if doc_url else ""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"欢迎来到 {project_name}"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"这是 **{project_name}** 的协作空间。\n"
                        "项目成员可以在这里同步进展、沉淀文档、跟踪任务与风险。"
                        f"{doc_line}"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "column_set",
                "flex_mode": "bisect",
                "background_style": "grey",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**建议先做**\n确认目标、成员与节奏",
                                },
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [
                            {
                                "tag": "div",
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**我能协助**\n任务跟踪、风险提醒、周报总结",
                                },
                            }
                        ],
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**常用指令**\n"
                        "• `/help` 查看帮助\n"
                        "• `/status` 查看项目状态\n"
                        "• `/tasks` 查看任务列表"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "建议把这条消息置顶，方便新成员快速进入状态。",
                },
            },
        ],
    }

from __future__ import annotations


def startup_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "TeamFlow 已启动"},
            "template": "blue",
        },
        "elements": [
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
                                "text": {
                                    "tag": "lark_md",
                                    "content": "**状态**: 已连接飞书\n**模式**: 运行中",
                                },
                            }
                        ],
                    }
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": '发送 **"开始创建项目"** 开始使用',
                },
            },
        ],
    }


def welcome_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "TeamFlow - AI 项目协作助手"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "我可以帮你管理项目，让协作更高效。",
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
                                    "content": '**创建项目**\n发送 "开始创建项目"',
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
                                    "content": "**查看状态**\n发送 /status（开发中）",
                                },
                            }
                        ],
                    },
                ],
            },
        ],
    }


def project_created_card(project_id: str, name: str, repo: str) -> dict:
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
                "text": {"tag": "lark_md", "content": f"**仓库**: {repo}"},
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


def project_create_form_card() -> dict:
    """Interactive card with a form for project creation (JSON 2.0)."""
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "创建新项目"},
            "template": "blue",
        },
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "form",
                    "name": "project_create_form",
                    "elements": [
                        {
                            "tag": "input",
                            "name": "project_name",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "请输入项目名称",
                            },
                            "label": {
                                "tag": "plain_text",
                                "content": "项目名称",
                            },
                        },
                        {
                            "tag": "input",
                            "name": "git_repo_path",
                            "placeholder": {
                                "tag": "plain_text",
                                "content": "https://github.com/org/repo",
                            },
                            "label": {
                                "tag": "plain_text",
                                "content": "Git 仓库地址",
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
                                                "content": "提交创建",
                                            },
                                            "type": "primary",
                                            "action_type": "form_submit",
                                            "name": "btn_submit",
                                            "value": {"teamflow_action": "submit_project_form"},
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
                                                "content": "重置",
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
                        "content": "如需取消，可直接忽略此卡片。",
                    },
                },
            ],
        },
    }


def project_failed_card(step: str, reason: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "项目创建失败"},
            "template": "red",
        },
        "elements": [
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
                    "content": "请重新发送 **\"开始创建项目\"** 重试。",
                },
            },
        ],
    }


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
                        f"🚀 这是 **{project_name}** 的 AI 协作空间。\n"
                        "我可以帮你跟踪任务、提醒风险和生成报告。"
                        f"{doc_line}"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**可用指令**\n"
                        "• /help — 查看帮助\n"
                        "• /status — 项目状态（开发中）\n"
                        "• /tasks — 任务列表（开发中）"
                    ),
                },
            },
        ],
    }

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
                    "content": "飞书协作空间初始化功能即将上线，届时将自动创建项目群和文档。",
                },
            },
        ],
    }


def project_create_form_card() -> dict:
    """Interactive card with a form for project creation (JSON 2.0)."""
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": "创建新项目"},
            "template": "blue",
        },
        "body": {
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

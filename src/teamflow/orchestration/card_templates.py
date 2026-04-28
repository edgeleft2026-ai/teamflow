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

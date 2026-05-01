from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    creating = "creating"
    created = "created"
    initializing_workspace = "initializing_workspace"
    active = "active"
    failed = "failed"
    archived = "archived"


class WorkspaceStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    partial_failed = "partial_failed"
    failed = "failed"


class EventStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    ignored = "ignored"


class ActionResult(StrEnum):
    success = "success"
    failure = "failure"


class MemberRole(StrEnum):
    admin = "admin"
    developer = "developer"
    viewer = "viewer"


class MemberStatus(StrEnum):
    active = "active"
    removed = "removed"


class BindingStatus(StrEnum):
    active = "active"
    revoked = "revoked"


class FlowState(StrEnum):
    """Conversation flow states for project creation wizard."""

    collecting_name = "collecting_project_name"
    collecting_repo = "collecting_repo"
    creating = "creating_project"
    created = "created"
    failed = "failed"


class FormStatus(StrEnum):
    """Project form submission status."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class InitStep(StrEnum):
    """Workspace initialization steps."""

    submitted = "表单已提交"
    create_record = "创建项目记录"
    create_repo = "创建代码仓库"
    publish_event = "发布项目事件"
    create_chat = "创建项目群"
    add_admin = "添加管理员入群"
    get_chat_link = "获取群链接"
    create_doc = "创建项目文档"
    transfer_owner = "转交文档所有权"
    send_welcome = "发送欢迎消息"
    complete = "完成创建"

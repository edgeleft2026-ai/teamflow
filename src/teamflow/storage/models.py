from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from teamflow.core.enums import (
    ActionResult,
    BindingStatus,
    EventStatus,
    MemberRole,
    MemberStatus,
    ProjectStatus,
    WorkspaceStatus,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str
    git_repo_path: str | None = Field(default=None)
    admin_open_id: str
    status: str = Field(default=ProjectStatus.creating)
    workspace_status: str = Field(default=WorkspaceStatus.pending)
    feishu_group_id: str | None = Field(default=None)
    feishu_group_link: str | None = Field(default=None)
    feishu_doc_url: str | None = Field(default=None)
    git_repo_platform: str | None = Field(default=None)
    git_repo_auto_created: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationState(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    open_id: str = Field(index=True)
    chat_id: str
    flow: str
    state: str
    payload: str = Field(default="{}")
    expires_at: datetime
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ProjectFormSubmission(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    request_id: str = Field(unique=True, index=True)
    open_id: str = Field(index=True)
    chat_id: str
    open_message_id: str = Field(index=True)
    project_name: str
    git_repo_path: str | None = Field(default=None)
    status: str = Field(default="pending", index=True)
    current_step: str = Field(default="表单已提交")
    steps_payload: str = Field(default="[]")
    project_id: str | None = Field(default=None, index=True)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EventLog(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    event_type: str = Field(index=True)
    idempotency_key: str = Field(unique=True)
    project_id: str | None = Field(default=None, index=True)
    source: str = "teamflow"
    payload: str = Field(default="{}")
    status: str = Field(default=EventStatus.pending)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    processed_at: datetime | None = Field(default=None)


class ActionLog(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    event_id: str | None = Field(default=None)
    action_name: str
    target: str | None = Field(default=None)
    input_summary: str = Field(default="{}")
    result: str = Field(default=ActionResult.success)
    output_summary: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = Field(default=None)


class UserIdentityBinding(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    open_id: str = Field(index=True, unique=True)
    gitea_username: str = Field(index=True)
    gitea_user_id: int | None = Field(default=None)
    email: str = Field(default="", index=True)
    status: str = Field(default=BindingStatus.active)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ProjectAccessBinding(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(index=True)
    feishu_chat_id: str = Field(index=True)
    gitea_org_name: str = Field(default="")
    gitea_team_id: int | None = Field(default=None)
    gitea_team_name: str = Field(default="")
    default_repo_permission: str = Field(default="write")
    status: str = Field(default=BindingStatus.active)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ProjectMember(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(index=True)
    open_id: str = Field(index=True)
    gitea_username: str = Field(default="")
    role: str = Field(default=MemberRole.developer)
    status: str = Field(default=MemberStatus.active)
    source: str = Field(default="chat_join")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

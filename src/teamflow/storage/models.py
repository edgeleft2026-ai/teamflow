from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from teamflow.core.enums import ActionResult, EventStatus, ProjectStatus, WorkspaceStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Project(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str
    git_repo_path: str
    admin_open_id: str
    status: str = Field(default=ProjectStatus.creating)
    workspace_status: str = Field(default=WorkspaceStatus.pending)
    feishu_group_id: str | None = Field(default=None)
    feishu_group_link: str | None = Field(default=None)
    feishu_doc_url: str | None = Field(default=None)
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

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

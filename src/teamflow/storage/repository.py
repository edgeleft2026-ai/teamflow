from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from teamflow.core.enums import ActionResult, EventStatus, ProjectStatus, WorkspaceStatus
from teamflow.storage.models import (
    ActionLog,
    ConversationState,
    EventLog,
    Project,
    ProjectFormSubmission,
)

logger = logging.getLogger(__name__)


class ProjectRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str, git_repo_path: str | None, admin_open_id: str) -> Project:
        project = Project(
            name=name,
            git_repo_path=git_repo_path,
            admin_open_id=admin_open_id,
            status=ProjectStatus.creating,
            workspace_status=WorkspaceStatus.pending,
        )
        self.session.add(project)
        self.session.flush()
        logger.info("创建项目记录: name=%s id=%s", name, project.id[:8])
        return project

    def get_by_id(self, project_id: str) -> Project | None:
        result = self.session.get(Project, project_id)
        if not result:
            logger.debug("项目未找到: %s", project_id[:8])
        return result

    def update_status(self, project_id: str, status: str) -> Project | None:
        project = self.get_by_id(project_id)
        if project:
            project.status = status
            project.updated_at = datetime.now(UTC)
            self.session.add(project)
            self.session.flush()
        return project

    def update_workspace(
        self,
        project_id: str,
        *,
        feishu_group_id: str | None = None,
        feishu_group_link: str | None = None,
        feishu_doc_url: str | None = None,
        workspace_status: str | None = None,
        status: str | None = None,
        git_repo_path: str | None = None,
        git_repo_platform: str | None = None,
        git_repo_auto_created: bool | None = None,
    ) -> Project | None:
        project = self.get_by_id(project_id)
        if project:
            if feishu_group_id is not None:
                project.feishu_group_id = feishu_group_id
            if feishu_group_link is not None:
                project.feishu_group_link = feishu_group_link
            if feishu_doc_url is not None:
                project.feishu_doc_url = feishu_doc_url
            if workspace_status is not None:
                project.workspace_status = workspace_status
            if status is not None:
                project.status = status
            if git_repo_path is not None:
                project.git_repo_path = git_repo_path
            if git_repo_platform is not None:
                project.git_repo_platform = git_repo_platform
            if git_repo_auto_created is not None:
                project.git_repo_auto_created = git_repo_auto_created
            project.updated_at = datetime.now(UTC)
            self.session.add(project)
            self.session.flush()
        return project


class ConversationStateRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active(self, open_id: str) -> ConversationState | None:
        stmt = (
            select(ConversationState)
            .where(
                ConversationState.open_id == open_id,
                ConversationState.expires_at > datetime.now(UTC),
            )
            .order_by(ConversationState.updated_at.desc())
        )
        return self.session.exec(stmt).first()

    def upsert(
        self,
        open_id: str,
        chat_id: str,
        flow: str,
        state: str,
        payload: dict,
        expires_at: datetime,
    ) -> ConversationState:
        existing = self.get_active(open_id)
        if existing:
            existing.chat_id = chat_id
            existing.flow = flow
            existing.state = state
            existing.payload = json.dumps(payload, ensure_ascii=False)
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(UTC)
            self.session.add(existing)
            self.session.flush()
            return existing

        conv = ConversationState(
            open_id=open_id,
            chat_id=chat_id,
            flow=flow,
            state=state,
            payload=json.dumps(payload, ensure_ascii=False),
            expires_at=expires_at,
        )
        self.session.add(conv)
        self.session.flush()
        return conv

    def delete(self, state_id: str) -> None:
        conv = self.session.get(ConversationState, state_id)
        if conv:
            self.session.delete(conv)
            self.session.flush()

    def delete_active(self, open_id: str) -> None:
        existing = self.get_active(open_id)
        if existing:
            self.session.delete(existing)
            self.session.flush()


class ProjectFormSubmissionRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_request_id(self, request_id: str) -> ProjectFormSubmission | None:
        stmt = select(ProjectFormSubmission).where(ProjectFormSubmission.request_id == request_id)
        return self.session.exec(stmt).first()

    def get_by_project_id(self, project_id: str) -> ProjectFormSubmission | None:
        stmt = select(ProjectFormSubmission).where(ProjectFormSubmission.project_id == project_id)
        return self.session.exec(stmt).first()

    def create(
        self,
        *,
        request_id: str,
        open_id: str,
        chat_id: str,
        open_message_id: str,
        project_name: str,
        git_repo_path: str | None,
        status: str,
        current_step: str,
        steps: list[dict],
    ) -> ProjectFormSubmission:
        submission = ProjectFormSubmission(
            request_id=request_id,
            open_id=open_id,
            chat_id=chat_id,
            open_message_id=open_message_id,
            project_name=project_name,
            git_repo_path=git_repo_path,
            status=status,
            current_step=current_step,
            steps_payload=json.dumps(steps, ensure_ascii=False),
        )
        self.session.add(submission)
        self.session.flush()
        return submission

    def update_progress(
        self,
        request_id: str,
        *,
        status: str,
        current_step: str,
        steps: list[dict],
        project_id: str | None = None,
        error_message: str | None = None,
    ) -> ProjectFormSubmission | None:
        submission = self.get_by_request_id(request_id)
        if submission:
            submission.status = status
            submission.current_step = current_step
            submission.steps_payload = json.dumps(steps, ensure_ascii=False)
            submission.project_id = project_id
            submission.error_message = error_message
            submission.updated_at = datetime.now(UTC)
            self.session.add(submission)
            self.session.flush()
        return submission


class EventLogRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        event_type: str,
        idempotency_key: str,
        project_id: str | None = None,
        source: str = "teamflow",
        payload: dict | None = None,
    ) -> EventLog:
        event = EventLog(
            event_type=event_type,
            idempotency_key=idempotency_key,
            project_id=project_id,
            source=source,
            payload=json.dumps(payload or {}, ensure_ascii=False),
            status=EventStatus.succeeded,
            processed_at=datetime.now(UTC),
        )
        self.session.add(event)
        self.session.flush()
        logger.info("创建事件日志: type=%s id=%s", event_type, event.id[:8])
        return event

    def exists_by_idempotency_key(self, key: str) -> bool:
        stmt = select(EventLog.id).where(EventLog.idempotency_key == key)
        return self.session.exec(stmt).first() is not None


class ActionLogRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        action_name: str,
        *,
        project_id: str | None = None,
        event_id: str | None = None,
        target: str | None = None,
        input_summary: dict | None = None,
        result: str = ActionResult.success,
        output_summary: dict | None = None,
        error_message: str | None = None,
    ) -> ActionLog:
        now = datetime.now(UTC)
        log = ActionLog(
            project_id=project_id,
            event_id=event_id,
            action_name=action_name,
            target=target,
            input_summary=json.dumps(input_summary or {}, ensure_ascii=False),
            result=result,
            output_summary=(
                json.dumps(output_summary or {}, ensure_ascii=False) if output_summary else None
            ),
            error_message=error_message,
            created_at=now,
            finished_at=now,
        )
        self.session.add(log)
        self.session.flush()
        return log

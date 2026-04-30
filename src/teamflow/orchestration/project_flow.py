from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from teamflow.access.parser import CardActionData
from teamflow.config import FeishuConfig
from teamflow.core.enums import ActionResult, ProjectStatus
from teamflow.execution.messages import send_card, send_text, update_card_message
from teamflow.orchestration.card_templates import (
    project_create_status_card,
    project_created_card,
    project_failed_card,
)
from teamflow.orchestration.event_bus import EventBus
from teamflow.storage.database import get_session
from teamflow.storage.models import ConversationState, ProjectFormSubmission
from teamflow.storage.repository import (
    ActionLogRepo,
    ConversationStateRepo,
    ProjectFormSubmissionRepo,
    ProjectRepo,
)

logger = logging.getLogger(__name__)

FLOW_NAME = "create_project"
EXPIRE_HOURS = 1

STATE_COLLECTING_NAME = "collecting_project_name"
STATE_COLLECTING_REPO = "collecting_repo"
STATE_CREATING = "creating_project"
STATE_CREATED = "created"
STATE_FAILED = "failed"

FORM_STATUS_RUNNING = "running"
FORM_STATUS_SUCCEEDED = "succeeded"
FORM_STATUS_FAILED = "failed"

STEP_SUBMITTED = "表单已提交"
STEP_CREATE_RECORD = "创建项目记录"
STEP_PUBLISH_EVENT = "发布项目事件"
STEP_CREATE_CHAT = "创建项目群"
STEP_ADD_ADMIN = "添加管理员入群"
STEP_GET_CHAT_LINK = "获取群链接"
STEP_CREATE_DOC = "创建项目文档"
STEP_TRANSFER_DOC_OWNER = "转交文档所有权"
STEP_SEND_WELCOME = "发送欢迎消息"
STEP_COMPLETE = "完成创建"

_HELP_TEXT = '当前正在创建项目。\n• 输入项目名称或仓库信息继续\n• 发送"取消"退出创建流程'

_START_TRIGGERS = {"取消", "exit", "cancel", "退出"}


@dataclass
class CardActionHandleResult:
    toast_type: str = "info"
    toast_text: str = ""
    card: dict | None = None


class ProjectCreateFlow:
    def __init__(
        self,
        feishu: FeishuConfig,
        session: Session,
        event_bus: EventBus,
    ) -> None:
        self.feishu = feishu
        self.session = session
        self.conv_repo = ConversationStateRepo(session)
        self.project_repo = ProjectRepo(session)
        self.action_repo = ActionLogRepo(session)
        self.submission_repo = ProjectFormSubmissionRepo(session)
        self.event_bus = event_bus

    def start(self, open_id: str, chat_id: str) -> None:
        """开始创建项目流程。"""
        self.conv_repo.delete_active(open_id)

        expires_at = datetime.now(UTC) + timedelta(hours=EXPIRE_HOURS)
        self.conv_repo.upsert(
            open_id=open_id,
            chat_id=chat_id,
            flow=FLOW_NAME,
            state=STATE_COLLECTING_NAME,
            payload={},
            expires_at=expires_at,
        )

        send_text(
            self.feishu,
            "好的，开始创建项目！\n\n请输入项目名称：",
            chat_id=chat_id,
        )
        self.action_repo.create(
            action_name="project_flow.start",
            target=open_id,
            input_summary={"trigger": "start_create"},
        )

    def handle(self, text: str, open_id: str, chat_id: str, conv: ConversationState) -> None:
        """根据当前会话状态处理用户输入。"""
        state = conv.state

        if text.strip() in _START_TRIGGERS:
            self.conv_repo.delete(conv.id)
            send_text(
                self.feishu,
                '已退出项目创建流程。需要时可以发送"开始创建项目"重新开始。',
                chat_id=chat_id,
            )
            return

        if state == STATE_COLLECTING_NAME:
            self._handle_collect_name(text, open_id, chat_id, conv)
        elif state == STATE_COLLECTING_REPO:
            self._handle_collect_repo(text, open_id, chat_id, conv)
        elif state == STATE_CREATING:
            send_text(self.feishu, "项目正在创建中，请稍候...", chat_id=chat_id)
        else:
            logger.warning("Unexpected conversation state: %s", state)
            self.conv_repo.delete(conv.id)

    def submit_form(self, card_data: CardActionData) -> CardActionHandleResult:
        """Accept a form submission and switch the original card into progress mode."""
        project_name = (card_data.form_values.get("project_name") or "").strip()
        git_repo_path = (card_data.form_values.get("git_repo_path") or "").strip()

        if not project_name or not git_repo_path:
            return CardActionHandleResult(
                toast_type="error",
                toast_text="请先填写项目名称和仓库地址",
            )

        request_id = self._resolve_request_id(card_data)
        existing = self.submission_repo.get_by_request_id(request_id)
        if existing:
            card = self._build_submission_card(existing)
            self._update_submission_card(existing.open_message_id, card)
            return CardActionHandleResult(
                toast_type="info",
                toast_text="该表单已提交，正在同步最新状态",
                card=card,
            )

        steps = self._build_initial_steps()
        submission = self.submission_repo.create(
            request_id=request_id,
            open_id=card_data.open_id,
            chat_id=card_data.chat_id,
            open_message_id=card_data.open_message_id,
            project_name=project_name,
            git_repo_path=git_repo_path,
            status=FORM_STATUS_RUNNING,
            current_step=STEP_CREATE_RECORD,
            steps=steps,
        )
        self.session.commit()

        card = self._build_submission_card(submission, steps_override=steps)
        self._update_submission_card(card_data.open_message_id, card)
        self._start_submission_worker(request_id)

        return CardActionHandleResult(
            toast_type="info",
            toast_text="已开始创建项目",
            card=card,
        )

    def _handle_collect_name(
        self,
        text: str,
        open_id: str,
        chat_id: str,
        conv: ConversationState,
    ) -> None:
        name = text.strip()
        if not name:
            send_text(self.feishu, "项目名称不能为空，请重新输入：", chat_id=chat_id)
            return

        payload = json.loads(conv.payload)
        payload["project_name"] = name

        expires_at = datetime.now(UTC) + timedelta(hours=EXPIRE_HOURS)
        self.conv_repo.upsert(
            open_id=open_id,
            chat_id=chat_id,
            flow=FLOW_NAME,
            state=STATE_COLLECTING_REPO,
            payload=payload,
            expires_at=expires_at,
        )

        send_text(
            self.feishu,
            f"项目名称：{name}\n\n请输入 Git 仓库地址或本地路径：",
            chat_id=chat_id,
        )

    def _handle_collect_repo(
        self,
        text: str,
        open_id: str,
        chat_id: str,
        conv: ConversationState,
    ) -> None:
        repo = text.strip()
        if not repo:
            send_text(self.feishu, "仓库地址不能为空，请重新输入：", chat_id=chat_id)
            return

        payload = json.loads(conv.payload)
        payload["git_repo_path"] = repo

        expires_at = datetime.now(UTC) + timedelta(hours=EXPIRE_HOURS)
        self.conv_repo.upsert(
            open_id=open_id,
            chat_id=chat_id,
            flow=FLOW_NAME,
            state=STATE_CREATING,
            payload=payload,
            expires_at=expires_at,
        )

        self._create_project(open_id, chat_id, payload)

    def _create_project(self, open_id: str, chat_id: str, payload: dict) -> None:
        """执行文本流程的项目创建：落库 + 发布事件 + 发送回执。"""
        project_name = payload["project_name"]
        git_repo_path = payload["git_repo_path"]

        try:
            project = self.project_repo.create(
                name=project_name,
                git_repo_path=git_repo_path,
                admin_open_id=open_id,
            )
            self.project_repo.update_status(project.id, ProjectStatus.created)

            self.event_bus.publish(
                event_type="project.created",
                idempotency_key=f"project.created:{project.id}",
                project_id=project.id,
                payload={
                    "project_name": project_name,
                    "git_repo_path": git_repo_path,
                    "admin_open_id": open_id,
                },
            )

            self.conv_repo.delete_active(open_id)

            send_card(
                self.feishu,
                project_created_card(project.id, project_name, git_repo_path),
                chat_id=chat_id,
            )

            self.action_repo.create(
                action_name="project_flow.create_project",
                project_id=project.id,
                target=project.id,
                input_summary={"name": project_name, "repo": git_repo_path},
            )

        except Exception as exc:
            logger.exception("Project creation failed for open_id=%s", open_id)
            self.action_repo.create(
                action_name="project_flow.create_project",
                target=open_id,
                input_summary={"name": project_name, "repo": git_repo_path},
                result=ActionResult.failure,
                error_message=str(exc),
            )

            self.conv_repo.delete_active(open_id)

            send_card(
                self.feishu,
                project_failed_card("创建项目记录", str(exc)),
                chat_id=chat_id,
            )

    def _start_submission_worker(self, request_id: str) -> None:
        worker = threading.Thread(
            target=self._run_submission_worker,
            args=(request_id,),
            daemon=True,
            name=f"project-create-{request_id[:8]}",
        )
        worker.start()

    def _run_submission_worker(self, request_id: str) -> None:
        with get_session() as session:
            flow = ProjectCreateFlow(self.feishu, session, EventBus(session))
            flow._process_submission(request_id)

    def _process_submission(self, request_id: str) -> None:
        submission = self.submission_repo.get_by_request_id(request_id)
        if not submission:
            logger.warning("Form submission not found: %s", request_id)
            return

        steps = self._load_submission_steps(submission)
        current_step = STEP_CREATE_RECORD
        project = None

        try:
            self._mark_step(
                steps,
                STEP_CREATE_RECORD,
                status="running",
                detail="正在写入项目记录",
            )
            self._persist_submission_progress(
                submission,
                status=FORM_STATUS_RUNNING,
                current_step=STEP_CREATE_RECORD,
                steps=steps,
            )

            project = self.project_repo.create(
                name=submission.project_name,
                git_repo_path=submission.git_repo_path,
                admin_open_id=submission.open_id,
            )
            self.project_repo.update_status(project.id, ProjectStatus.created)
            self._mark_step(
                steps,
                STEP_CREATE_RECORD,
                status="success",
                detail=f"项目记录已创建，ID: {project.id[:8]}",
            )
            self._persist_submission_progress(
                submission,
                status=FORM_STATUS_RUNNING,
                current_step=STEP_PUBLISH_EVENT,
                steps=steps,
                project_id=project.id,
            )

            current_step = STEP_PUBLISH_EVENT
            self._mark_step(
                steps,
                STEP_PUBLISH_EVENT,
                status="running",
                detail="正在通知下游初始化工作空间",
            )
            self._persist_submission_progress(
                submission,
                status=FORM_STATUS_RUNNING,
                current_step=STEP_PUBLISH_EVENT,
                steps=steps,
                project_id=project.id,
            )

            self.event_bus.publish(
                event_type="project.created",
                idempotency_key=f"project.created:{project.id}",
                project_id=project.id,
                payload={
                    "project_name": submission.project_name,
                    "git_repo_path": submission.git_repo_path,
                    "admin_open_id": submission.open_id,
                },
            )
            self._mark_step(
                steps,
                STEP_PUBLISH_EVENT,
                status="success",
                detail="创建事件已发布",
            )
            self._mark_step(
                steps,
                STEP_CREATE_CHAT,
                status="pending",
                detail="等待开始",
            )

            self.conv_repo.delete_active(submission.open_id)
            self.action_repo.create(
                action_name="project_flow.create_project_form",
                project_id=project.id,
                target=project.id,
                input_summary={
                    "name": submission.project_name,
                    "repo": submission.git_repo_path,
                    "request_id": request_id,
                },
            )
            self._persist_submission_progress(
                submission,
                status=FORM_STATUS_RUNNING,
                current_step=STEP_CREATE_CHAT,
                steps=steps,
                project_id=project.id,
            )
        except Exception as exc:
            logger.exception("Project form submission failed: request_id=%s", request_id)
            self.session.rollback()

            submission = self.submission_repo.get_by_request_id(request_id)
            if not submission:
                return

            steps = self._load_submission_steps(submission)
            self._mark_step(
                steps,
                current_step,
                status="failure",
                detail=str(exc),
            )
            self.action_repo.create(
                action_name="project_flow.create_project_form",
                target=submission.open_id,
                input_summary={
                    "name": submission.project_name,
                    "repo": submission.git_repo_path,
                    "request_id": request_id,
                },
                result=ActionResult.failure,
                error_message=str(exc),
            )
            self._persist_submission_progress(
                submission,
                status=FORM_STATUS_FAILED,
                current_step=current_step,
                steps=steps,
                project_id=project.id if project else None,
                error_message=str(exc),
            )

    def _persist_submission_progress(
        self,
        submission: ProjectFormSubmission,
        *,
        status: str,
        current_step: str,
        steps: list[dict],
        project_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        updated = self.submission_repo.update_progress(
            submission.request_id,
            status=status,
            current_step=current_step,
            steps=steps,
            project_id=project_id,
            error_message=error_message,
        )
        self.session.commit()

        if updated:
            card = self._build_submission_card(updated, steps_override=steps)
            self._update_submission_card(updated.open_message_id, card)

    def _build_submission_card(
        self,
        submission: ProjectFormSubmission,
        *,
        steps_override: list[dict] | None = None,
    ) -> dict:
        steps = steps_override or self._load_submission_steps(submission)
        return project_create_status_card(
            status=submission.status,
            project_name=submission.project_name,
            git_repo_path=submission.git_repo_path,
            steps=steps,
            current_step=submission.current_step,
            project_id=submission.project_id,
            error_message=submission.error_message,
        )

    def _resolve_request_id(self, card_data: CardActionData) -> str:
        request_id = (card_data.action_value.get("request_id") or "").strip()
        if request_id:
            return request_id
        if card_data.open_message_id:
            return card_data.open_message_id
        return f"{card_data.open_id}:{card_data.token}"

    def _build_initial_steps(self) -> list[dict]:
        return [
            {"name": STEP_SUBMITTED, "status": "success", "detail": "表单内容已锁定"},
            {"name": STEP_CREATE_RECORD, "status": "running", "detail": "等待开始"},
            {"name": STEP_PUBLISH_EVENT, "status": "pending", "detail": "等待开始"},
            {"name": STEP_CREATE_CHAT, "status": "pending", "detail": "等待开始"},
            {"name": STEP_ADD_ADMIN, "status": "pending", "detail": "等待开始"},
            {"name": STEP_GET_CHAT_LINK, "status": "pending", "detail": "等待开始"},
            {"name": STEP_CREATE_DOC, "status": "pending", "detail": "等待开始"},
            {"name": STEP_TRANSFER_DOC_OWNER, "status": "pending", "detail": "等待开始"},
            {"name": STEP_SEND_WELCOME, "status": "pending", "detail": "等待开始"},
            {"name": STEP_COMPLETE, "status": "pending", "detail": "等待所有步骤完成"},
        ]

    def _load_submission_steps(self, submission: ProjectFormSubmission) -> list[dict]:
        try:
            steps = json.loads(submission.steps_payload)
        except json.JSONDecodeError:
            logger.warning("Invalid submission steps payload: %s", submission.request_id)
            return self._build_initial_steps()
        return steps if isinstance(steps, list) else self._build_initial_steps()

    def _mark_step(
        self,
        steps: list[dict],
        step_name: str,
        *,
        status: str,
        detail: str,
    ) -> None:
        for step in steps:
            if step.get("name") == step_name:
                step["status"] = status
                step["detail"] = detail
                return

        steps.append({"name": step_name, "status": status, "detail": detail})

    def _update_submission_card(self, open_message_id: str, card: dict) -> None:
        if not open_message_id:
            return

        result = update_card_message(self.feishu, open_message_id, card)
        if not result.success:
            logger.warning("Failed to update submission card: %s", result.error)

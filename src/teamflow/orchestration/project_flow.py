from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from teamflow.config import FeishuConfig
from teamflow.core.enums import ActionResult, ProjectStatus
from teamflow.execution.messages import send_text
from teamflow.orchestration.event_bus import EventBus
from teamflow.storage.models import ConversationState
from teamflow.storage.repository import ActionLogRepo, ConversationStateRepo, ProjectRepo

logger = logging.getLogger(__name__)

FLOW_NAME = "create_project"
EXPIRE_HOURS = 1

STATE_COLLECTING_NAME = "collecting_project_name"
STATE_COLLECTING_REPO = "collecting_repo"
STATE_CREATING = "creating_project"
STATE_CREATED = "created"
STATE_FAILED = "failed"

_HELP_TEXT = (
    "当前正在创建项目。\n"
    "• 输入项目名称或仓库信息继续\n"
    "• 发送\"取消\"退出创建流程"
)

_START_TRIGGERS = {"取消", "exit", "cancel", "退出"}


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
        self.event_bus = event_bus

    def start(self, open_id: str, chat_id: str) -> None:
        """开始创建项目流程。"""
        # 清除旧的活跃会话（允许重新开始）
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

        # 用户中途取消
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

    def _handle_collect_name(
        self, text: str, open_id: str, chat_id: str, conv: ConversationState,
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
        self, text: str, open_id: str, chat_id: str, conv: ConversationState,
    ) -> None:
        repo = text.strip()
        if not repo:
            send_text(self.feishu, "仓库地址不能为空，请重新输入：", chat_id=chat_id)
            return

        payload = json.loads(conv.payload)
        payload["git_repo_path"] = repo

        # Update state to creating
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
        """执行项目创建：落库 + 发布事件 + 发送回执。"""
        project_name = payload["project_name"]
        git_repo_path = payload["git_repo_path"]

        try:
            project = self.project_repo.create(
                name=project_name,
                git_repo_path=git_repo_path,
                admin_open_id=open_id,
            )
            self.project_repo.update_status(project.id, ProjectStatus.created)

            # 发布 project.created 事件
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

            # 清除会话状态
            self.conv_repo.delete_active(open_id)

            send_text(
                self.feishu,
                (
                    f"项目创建成功！\n\n"
                    f"项目ID：{project.id[:8]}\n"
                    f"项目名：{project_name}\n"
                    f"仓库：{git_repo_path}\n\n"
                    f"接下来将自动初始化飞书协作空间..."
                ),
                chat_id=chat_id,
            )

            self.action_repo.create(
                action_name="project_flow.create_project",
                project_id=project.id,
                target=project.id,
                input_summary={"name": project_name, "repo": git_repo_path},
            )

        except Exception as e:
            logger.exception("Project creation failed for open_id=%s", open_id)
            self.action_repo.create(
                action_name="project_flow.create_project",
                target=open_id,
                input_summary={"name": project_name, "repo": git_repo_path},
                result=ActionResult.failure,
                error_message=str(e),
            )

            self.conv_repo.delete_active(open_id)

            send_text(
                self.feishu,
                (
                    f"项目创建失败\n\n"
                    f"失败步骤：创建项目记录\n"
                    f"原因：{e}\n\n"
                    f"你可以重新发送\"开始创建项目\"重试。"
                ),
                chat_id=chat_id,
            )

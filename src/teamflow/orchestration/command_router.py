from __future__ import annotations

import logging

from teamflow.config import FeishuConfig
from teamflow.execution.messages import send_card
from teamflow.orchestration.card_templates import project_create_form_card, welcome_card
from teamflow.orchestration.event_bus import EventBus
from teamflow.orchestration.project_flow import FLOW_NAME, ProjectCreateFlow
from teamflow.storage.database import get_session
from teamflow.storage.repository import ConversationStateRepo

logger = logging.getLogger(__name__)

_HELP_TRIGGERS = {"/help", "帮助", "help"}
_CREATE_TRIGGERS = {"开始创建项目", "创建项目", "新建项目", "create project"}


class CommandRouter:
    def __init__(self, feishu: FeishuConfig) -> None:
        self.feishu = feishu

    def handle(self, text: str, open_id: str, chat_id: str) -> None:
        """处理一条用户消息，路由到对应的处理器。"""
        stripped = text.strip()

        with get_session() as session:
            conv_repo = ConversationStateRepo(session)
            event_bus = EventBus(session)
            flow = ProjectCreateFlow(self.feishu, session, event_bus)

            # 优先检查是否有活跃的创建流程
            active_conv = conv_repo.get_active(open_id)

            if active_conv and active_conv.flow == FLOW_NAME:
                flow.handle(stripped, open_id, chat_id, active_conv)
                return

            # 无活跃流程，匹配指令
            if stripped in _CREATE_TRIGGERS:
                result = send_card(self.feishu, project_create_form_card(), chat_id=chat_id)
                if not result.success:
                    logger.error("Failed to send form card: %s", result.error)
                return

        if stripped in _HELP_TRIGGERS:
            send_card(self.feishu, welcome_card(), chat_id=chat_id)
            return

        # 无法识别 — 发送引导
        send_card(self.feishu, welcome_card(), chat_id=chat_id)

    def handle_card_action(self, card_data) -> None:
        """Route a card action event to the appropriate handler."""
        action_value = card_data.action_value
        teamflow_action = action_value.get("teamflow_action", "")

        with get_session() as session:
            event_bus = EventBus(session)
            flow = ProjectCreateFlow(self.feishu, session, event_bus)

            if teamflow_action == "submit_project_form":
                flow.create_from_form(
                    open_id=card_data.open_id,
                    chat_id=card_data.chat_id,
                    form_values=card_data.form_values,
                )
                return

        logger.warning("Unknown card action: %s", teamflow_action)

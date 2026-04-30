"""Workspace initialization orchestration — triggered by project.created events.

Uses the Agent smart channel as the primary path and falls back to
direct SDK calls (deterministic channel) if the Agent fails.
"""

from __future__ import annotations

import asyncio
import json
import logging

from teamflow.ai.agent import AgentExecutor
from teamflow.ai.skills import registry
from teamflow.config import FeishuConfig
from teamflow.core.enums import ActionResult, ProjectStatus, WorkspaceStatus
from teamflow.execution.messages import send_card_async, send_text_async
from teamflow.orchestration.card_templates import (
    workspace_init_result_card,
    workspace_welcome_card,
)
from teamflow.orchestration.event_bus import EventBus
from teamflow.storage.models import EventLog
from teamflow.storage.repository import ActionLogRepo, ProjectRepo

logger = logging.getLogger(__name__)

_MAX_PROJECT_NAME_LEN = 80


async def _send_text_receipt_async(feishu, project, steps: list[dict]) -> None:
    """Fallback: send a plain-text version of the admin receipt (async)."""
    from teamflow.execution.messages import send_text_async

    lines = [f"工作空间初始化结果 | {project.name}", ""]
    for s in steps:
        status = s.get("status", "unknown")
        icon = {"success": "[OK]", "failure": "[FAIL]", "skipped": "[SKIP]"}.get(status, "[?]")
        lines.append(f"  {icon} {s.get('name', '?')}: {s.get('detail', '')}")
    result = await send_text_async(feishu, "\n".join(lines), user_id=project.admin_open_id)
    if result.success:
        logger.info("Admin text receipt sent OK")
    else:
        logger.error("Admin text receipt also failed: %s", result.error)


class WorkspaceInitFlow:
    """Orchestrates Feishu workspace initialization after a project is created."""

    def __init__(
        self,
        feishu: FeishuConfig,
        agent_executor: AgentExecutor,
        session_factory,
        max_iterations: int = 10,
    ) -> None:
        self.feishu = feishu
        self.agent_executor = agent_executor
        self.session_factory = session_factory
        self.max_iterations = max_iterations

    def on_project_created(self, event: EventLog) -> None:
        """Synchronous entry point called by EventBus.

        Extracts data immediately (before the publishing session closes),
        then spins up an asyncio task so the event dispatcher is not blocked.
        """
        # Read ORM attributes now — the session will close before the async task runs.
        project_id = event.project_id
        event_id = event.id
        if not project_id:
            logger.error("Event %s has no project_id, skipping", event_id[:8])
            return

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._run(project_id, event_id))
            else:
                asyncio.run(self._run(project_id, event_id))
        except Exception:
            logger.exception("Failed to start workspace init async task")

    async def _run(self, project_id: str, event_id: str) -> None:
        with self.session_factory() as session:
            project_repo = ProjectRepo(session)
            action_repo = ActionLogRepo(session)
            event_bus = EventBus(session)

            # 1. Load project
            project = project_repo.get_by_id(project_id)
            if not project:
                logger.error("Project not found: %s", project_id[:8])
                return

            # 2. Idempotency: skip if already fully initialized
            if project.workspace_status in (
                WorkspaceStatus.succeeded,
                WorkspaceStatus.partial_failed,
            ):
                logger.info(
                    "Project %s workspace already initialized (%s), skipping",
                    project.id[:8],
                    project.workspace_status,
                )
                return

            # 3. Mark as running
            project_repo.update_workspace(
                project_id=project.id,
                workspace_status=WorkspaceStatus.running,
                status=ProjectStatus.initializing_workspace,
            )
            session.commit()

            # 4. Execute initialization
            steps: list[dict] = []
            chat_id = project.feishu_group_id
            doc_url = project.feishu_doc_url
            group_link = project.feishu_group_link

            try:
                agent_out = await self._execute_agent_channel(project)
                steps.extend(agent_out.get("steps", []))
                chat_id = agent_out.get("chat_id") or chat_id
                doc_url = agent_out.get("doc_url") or doc_url
                group_link = agent_out.get("group_link") or group_link
                agent_ok = agent_out.get("agent_success", False)
            except Exception:
                logger.exception("Agent channel crashed")
                agent_ok = False
                action_repo.create(
                    action_name="workspace_init.agent",
                    project_id=project.id,
                    event_id=event_id,
                    result=ActionResult.failure,
                    error_message="Agent channel crashed",
                )

            if not agent_ok:
                try:
                    fallback = await self._execute_deterministic_channel(
                        project,
                        chat_id=chat_id,
                        doc_url=doc_url,
                        group_link=group_link,
                    )
                    steps.extend(fallback.get("steps", []))
                    chat_id = fallback.get("chat_id") or chat_id
                    doc_url = fallback.get("doc_url") or doc_url
                    group_link = fallback.get("group_link") or group_link
                except Exception:
                    logger.exception("Deterministic channel also crashed")
                    steps.append(
                        {
                            "name": "工作空间初始化",
                            "status": "failure",
                            "detail": "Agent 和降级通道均失败",
                        }
                    )

            # 5. Determine final status
            has_chat = bool(chat_id)
            has_doc = bool(doc_url)
            if has_chat and has_doc:
                ws_status = WorkspaceStatus.succeeded
                proj_status = ProjectStatus.active
            elif has_chat or has_doc:
                ws_status = WorkspaceStatus.partial_failed
                proj_status = ProjectStatus.active
            else:
                ws_status = WorkspaceStatus.failed
                proj_status = ProjectStatus.failed

            # 6. Write back
            project_repo.update_workspace(
                project_id=project.id,
                feishu_group_id=chat_id,
                feishu_group_link=group_link,
                feishu_doc_url=doc_url,
                workspace_status=ws_status,
                status=proj_status,
            )
            session.commit()

            # 7. Admin receipt — try card, fallback to text
            try:
                receipt = await send_card_async(
                    self.feishu,
                    workspace_init_result_card(project.name, steps),
                    user_id=project.admin_open_id,
                )
                if not receipt.success:
                    logger.warning("Admin receipt card failed, trying text: %s", receipt.error)
                    await _send_text_receipt_async(self.feishu, project, steps)
            except Exception:
                logger.exception("Failed to send admin receipt, trying text fallback")
                await _send_text_receipt_async(self.feishu, project, steps)

            # 8. Group welcome
            if chat_id:
                try:
                    welcome = await send_card_async(
                        self.feishu,
                        workspace_welcome_card(project.name, doc_url),
                        chat_id=chat_id,
                    )
                    if not welcome.success:
                        logger.warning("Welcome card failed, trying text: %s", welcome.error)
                        txt = f"欢迎来到 {project.name} 项目！\n这是 TeamFlow AI 协作空间。"
                        if doc_url:
                            txt += f"\n项目文档: {doc_url}"
                        await send_text_async(self.feishu, txt, chat_id=chat_id)
                except Exception:
                    logger.exception("Failed to send group welcome")

            # 9. Publish workspace_initialized event
            event_bus.publish(
                event_type="project.workspace_initialized",
                idempotency_key=f"project.workspace_initialized:{project.id}",
                project_id=project.id,
                payload={
                    "workspace_status": ws_status,
                    "feishu_group_id": chat_id,
                    "feishu_doc_url": doc_url,
                },
            )

    async def _execute_agent_channel(self, project) -> dict:
        """Run the workspace_init skill through the Agent Executor.

        Returns a dict with steps, chat_id, doc_url, group_link, agent_success.
        """
        task = registry.build_task(
            description="Initialize Feishu workspace for project",
            context={
                "project_name": project.name,
                "admin_open_id": project.admin_open_id,
                "git_repo_path": project.git_repo_path,
            },
            skill_name="workspace_init",
            complexity="smart",
            max_iterations=self.max_iterations,
        )
        agent_result = await self.agent_executor.execute(task)

        steps: list[dict] = []
        chat_id: str | None = None
        doc_url: str | None = None
        group_link: str | None = None

        for action in agent_result.actions:
            tool_name = action.get("tool", "")
            tool_result = action.get("result", {})
            success = tool_result.get("success", False)
            error = tool_result.get("error", "")
            raw_result = tool_result.get("result", ["{}"])

            try:
                result_data = json.loads(raw_result[0]) if raw_result else {}
            except Exception:
                result_data = {}

            if tool_name == "im.v1.chat.create":
                if success:
                    chat_id = result_data.get("chat_id")
                    steps.append(
                        {
                            "name": "创建项目群",
                            "status": "success",
                            "detail": f"群ID: {chat_id}",
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "创建项目群",
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

            elif tool_name == "im.v1.chat.members.create":
                if success:
                    steps.append(
                        {
                            "name": "添加管理员入群",
                            "status": "success",
                            "detail": "管理员已加入",
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "添加管理员入群",
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

            elif tool_name == "im.v1.chat.link":
                if success:
                    group_link = result_data.get("share_link")
                    steps.append(
                        {
                            "name": "获取群链接",
                            "status": "success",
                            "detail": group_link or "已获取",
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "获取群链接",
                            "status": "failure",
                            "detail": error or "无法获取",
                        }
                    )

            elif tool_name == "docx.v1.document.create":
                if success:
                    doc_url = result_data.get("url")
                    steps.append(
                        {
                            "name": "创建项目文档",
                            "status": "success",
                            "detail": doc_url or "已创建",
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "创建项目文档",
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

            elif tool_name == "im.v1.message.create":
                if success:
                    steps.append(
                        {
                            "name": "发送欢迎消息",
                            "status": "success",
                            "detail": "已发送",
                        }
                    )
                else:
                    steps.append(
                        {
                            "name": "发送欢迎消息",
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

        if not agent_result.success and not steps:
            steps.append(
                {
                    "name": "Agent 执行",
                    "status": "failure",
                    "detail": agent_result.error or "执行失败",
                }
            )

        return {
            "steps": steps,
            "chat_id": chat_id,
            "doc_url": doc_url,
            "group_link": group_link,
            "agent_success": agent_result.success,
        }

    async def _execute_deterministic_channel(
        self,
        project,
        *,
        chat_id: str | None = None,
        doc_url: str | None = None,
        group_link: str | None = None,
    ) -> dict:
        """Direct SDK calls as a fallback when the Agent channel fails.

        Skips steps for which the resource already exists.
        """
        from teamflow.ai.tools.feishu import (
            _add_members_to_chat,
            _create_chat,
            _create_document,
            _get_chat_link,
            _send_message,
        )

        steps: list[dict] = []

        # Step 1: Create chat
        if not chat_id:
            try:
                name = f"TeamFlow | {project.name}"
                if len(name) > _MAX_PROJECT_NAME_LEN:
                    name = name[:_MAX_PROJECT_NAME_LEN].rstrip()
                result = await _create_chat(
                    name=name,
                    description="AI 驱动的项目协作空间",
                )
                chat_id = result.get("chat_id")
                steps.append(
                    {
                        "name": "创建项目群",
                        "status": "success",
                        "detail": f"群ID: {chat_id}",
                    }
                )
            except Exception as e:
                logger.exception("Failed to create chat")
                steps.append(
                    {"name": "创建项目群", "status": "failure", "detail": str(e)}
                )

        # Step 2: Add admin
        if chat_id and project.admin_open_id:
            try:
                await _add_members_to_chat(chat_id, [project.admin_open_id])
                steps.append(
                    {
                        "name": "添加管理员入群",
                        "status": "success",
                        "detail": "管理员已加入",
                    }
                )
            except Exception as e:
                logger.exception("Failed to add admin to chat")
                steps.append(
                    {
                        "name": "添加管理员入群",
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        # Step 3: Get chat link
        if chat_id and not group_link:
            try:
                result = await _get_chat_link(chat_id)
                group_link = result.get("share_link")
                steps.append(
                    {
                        "name": "获取群链接",
                        "status": "success",
                        "detail": group_link or "已获取",
                    }
                )
            except Exception as e:
                logger.warning("Failed to get chat link: %s", e)
                steps.append(
                    {
                        "name": "获取群链接",
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        # Step 4: Create document
        if not doc_url:
            try:
                result = await _create_document(title=f"{project.name} - 项目文档")
                doc_url = result.get("url")
                doc_id = result.get("document_id")
                steps.append(
                    {
                        "name": "创建项目文档",
                        "status": "success",
                        "detail": doc_url or "已创建",
                    }
                )
                # Share document with admin so they can manage it
                if doc_id and project.admin_open_id:
                    try:
                        from teamflow.ai.tools.feishu import _add_document_collaborator
                        await _add_document_collaborator(doc_id, project.admin_open_id)
                        logger.info("Document shared with admin: %s", doc_id)
                    except Exception as e:
                        logger.warning("Failed to share document with admin: %s", e)
            except Exception as e:
                logger.exception("Failed to create document")
                steps.append(
                    {
                        "name": "创建项目文档",
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        # Step 5: Send welcome message
        if chat_id:
            try:
                card = workspace_welcome_card(project.name, doc_url)
                await _send_message(
                    receive_id=chat_id,
                    content=json.dumps(card, ensure_ascii=False),
                    msg_type="interactive",
                )
                steps.append(
                    {
                        "name": "发送欢迎消息",
                        "status": "success",
                        "detail": "已发送",
                    }
                )
            except Exception as e:
                logger.exception("Failed to send welcome message")
                steps.append(
                    {
                        "name": "发送欢迎消息",
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        return {
            "steps": steps,
            "chat_id": chat_id,
            "doc_url": doc_url,
            "group_link": group_link,
        }

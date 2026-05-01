"""Workspace initialization orchestration — triggered by project.created events.

Uses the Agent smart channel as the primary path and falls back to
direct SDK calls (deterministic channel) if the Agent fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable

from teamflow.ai.agent import AgentExecutor
from teamflow.ai.skills import registry
from teamflow.config import FeishuConfig
from teamflow.core.enums import ActionResult, FormStatus, InitStep, ProjectStatus, WorkspaceStatus
from teamflow.execution.messages import send_card_async, send_text_async, update_card_message_async
from teamflow.orchestration.card_templates import (
    project_create_status_card,
    workspace_init_result_card,
    workspace_welcome_card,
)
from teamflow.orchestration.event_bus import EventBus
from teamflow.storage.models import EventLog
from teamflow.storage.repository import ActionLogRepo, ProjectFormSubmissionRepo, ProjectRepo

logger = logging.getLogger(__name__)

_MAX_PROJECT_NAME_LEN = 80


def _try_parse_agent_json(summary: str) -> dict | None:
    """Try to extract a structured JSON block from the Agent's summary output.

    Returns the parsed dict if found, None otherwise.
    """
    import re

    json_match = re.search(r"```json\s*([\s\S]*?)```", summary)
    if not json_match:
        return None
    try:
        data = json.loads(json_match.group(1).strip())
        if isinstance(data, dict) and "chat_id" in data:
            return data
    except json.JSONDecodeError:
        logger.debug("Agent JSON 解析失败，回退到 action 遍历")
    return None

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
        logger.info("管理员文本回执发送成功")
    else:
        logger.error("管理员文本回执也发送失败: %s", result.error)

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
            logger.error("事件 %s 缺少 project_id，跳过", event_id[:8])
            return

        try:
            loop = asyncio.get_running_loop()
        except Exception:
            worker = threading.Thread(
                target=lambda: asyncio.run(self._run(project_id, event_id)),
                daemon=True,
                name=f"workspace-init-{project_id[:8]}",
            )
            worker.start()
            return

        try:
            loop.create_task(self._run(project_id, event_id))
        except Exception:
            logger.exception("启动工作空间初始化异步任务失败")

    async def _run(self, project_id: str, event_id: str) -> None:
        with self.session_factory() as session:
            project_repo = ProjectRepo(session)
            submission_repo = ProjectFormSubmissionRepo(session)
            action_repo = ActionLogRepo(session)
            event_bus = EventBus(session)

            # 1. Load project
            project = project_repo.get_by_id(project_id)
            if not project:
                logger.error("项目未找到: %s", project_id[:8])
                return

            # 2. Idempotency: skip if already fully initialized
            if project.workspace_status in (
                WorkspaceStatus.succeeded,
                WorkspaceStatus.partial_failed,
            ):
                logger.info(
                    "项目 %s 工作空间已初始化 (%s)，跳过",
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

            submission = submission_repo.get_by_project_id(project.id)
            submission_steps = self._load_submission_steps(submission) if submission else []
            if submission:
                await self._sync_submission_card(
                    session,
                    submission_repo,
                    submission,
                    status=FormStatus.running,
                    current_step=InitStep.create_chat,
                    steps=submission_steps,
                    project_id=project.id,
                )

            # 4. Execute initialization
            steps: list[dict] = []
            chat_id = project.feishu_group_id
            doc_url = project.feishu_doc_url
            document_id = self._extract_doc_token(doc_url)
            group_link = project.feishu_group_link

            async def report_step(step: dict) -> None:
                if not submission:
                    return
                self._upsert_step(
                    submission_steps,
                    step.get("name", "未知步骤"),
                    status=step.get("status", "pending"),
                    detail=step.get("detail", ""),
                )
                await self._sync_submission_card(
                    session,
                    submission_repo,
                    submission,
                    status=FormStatus.running,
                    current_step=step.get("name", InitStep.create_chat),
                    steps=submission_steps,
                    project_id=project.id,
                )

            try:
                agent_out = await self._execute_agent_channel(project, on_step=report_step)
                steps.extend(agent_out.get("steps", []))
                chat_id = agent_out.get("chat_id") or chat_id
                doc_url = agent_out.get("doc_url") or doc_url
                document_id = agent_out.get("document_id") or document_id
                group_link = agent_out.get("group_link") or group_link
                agent_ok = agent_out.get("agent_success", False)
            except Exception:
                logger.exception("Agent 通道崩溃")
                agent_ok = False
                action_repo.create(
                    action_name="workspace_init.agent",
                    project_id=project.id,
                    event_id=event_id,
                    result=ActionResult.failure,
                    error_message="Agent channel crashed",
                )

            if not agent_ok:
                if submission:
                    self._upsert_step(
                        submission_steps,
                        InitStep.create_chat,
                        status="running",
                        detail="Agent 通道未完成，正在切换降级通道",
                    )
                    await self._sync_submission_card(
                        session,
                        submission_repo,
                        submission,
                        status=FormStatus.running,
                        current_step=InitStep.create_chat,
                        steps=submission_steps,
                        project_id=project.id,
                    )
                try:
                    fallback = await self._execute_deterministic_channel(
                        project,
                        chat_id=chat_id,
                        doc_url=doc_url,
                        group_link=group_link,
                        on_step=report_step,
                    )
                    steps.extend(fallback.get("steps", []))
                    chat_id = fallback.get("chat_id") or chat_id
                    doc_url = fallback.get("doc_url") or doc_url
                    document_id = fallback.get("document_id") or document_id
                    group_link = fallback.get("group_link") or group_link
                except Exception:
                    logger.exception("降级通道也崩溃")
                    steps.append(
                        {
                            "name": InitStep.create_chat,
                            "status": "failure",
                            "detail": "Agent 和降级通道均失败",
                        }
                    )

            owner_transfer_ok = not bool(doc_url)
            if document_id and project.admin_open_id:
                owner_transfer_ok = await self._ensure_document_owner(
                    document_id=document_id,
                    admin_open_id=project.admin_open_id,
                    report_step=report_step,
                )

            # 5. Determine final status
            has_chat = bool(chat_id)
            has_doc = bool(doc_url)
            if has_chat and has_doc and owner_transfer_ok:
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

            if submission:
                self._upsert_step(
                    submission_steps,
                    InitStep.complete,
                    status="running",
                    detail="等待欢迎消息发送完成",
                )
                self._upsert_step(
                    submission_steps,
                    InitStep.send_welcome,
                    status="running",
                    detail="正在发送欢迎消息",
                )
                await self._sync_submission_card(
                    session,
                    submission_repo,
                    submission,
                    status=FormStatus.running,
                    current_step=InitStep.send_welcome,
                    steps=submission_steps,
                    project_id=project.id,
                )

            # 7. 管理员回执 — 如果创建卡片已关联，以卡片为唯一信息源
            if not submission:
                try:
                    receipt = await send_card_async(
                        self.feishu,
                        workspace_init_result_card(project.name, steps),
                        user_id=project.admin_open_id,
                    )
                    if not receipt.success:
                        logger.warning("管理员回执卡片发送失败，尝试文本: %s", receipt.error)
                        await _send_text_receipt_async(self.feishu, project, steps)
                except Exception:
                    logger.exception("发送管理员回执失败，尝试文本降级")
                    await _send_text_receipt_async(self.feishu, project, steps)

            # 8. Publish workspace_initialized event
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

            # 8.5 Ensure Gitea Team for project access control
            if chat_id and project.git_repo_path:
                try:
                    from teamflow.config.settings import load_config
                    from teamflow.orchestration.access_sync import AccessSyncFlow

                    settings = load_config()
                    gitea_cfg = settings.gitea
                    if gitea_cfg and gitea_cfg.base_url and gitea_cfg.access_token:
                        org_name = gitea_cfg.org_name or ""
                        if org_name:
                            team_id = await AccessSyncFlow.ensure_project_team(
                                gitea_config=gitea_cfg,
                                project_id=project.id,
                                project_name=project.name,
                                chat_id=chat_id,
                                org_name=org_name,
                                repo_full_name=project.git_repo_path,
                            )
                            if team_id:
                                logger.info(
                                    "项目 Team 已就绪: project=%s team_id=%d",
                                    project.id[:8], team_id,
                                )
                            else:
                                logger.warning(
                                    "项目 Team 创建失败: project=%s",
                                    project.id[:8],
                                )
                except Exception:
                    logger.exception("Gitea Team 创建异常: project=%s", project.id[:8])

            # 9. Group welcome — send only after workspace initialization has been finalized.
            welcome_step = await self._send_group_welcome(
                project.name,
                chat_id=chat_id,
                doc_url=doc_url,
            )
            if submission and welcome_step:
                self._upsert_step(
                    submission_steps,
                    InitStep.send_welcome,
                    status=welcome_step["status"],
                    detail=welcome_step["detail"],
                )
                final_submission_status = FormStatus.failed
                final_current_step = "创建未完成"
                final_detail = "项目创建流程仍有未完成步骤"

                if ws_status == WorkspaceStatus.succeeded and welcome_step["status"] == "success":
                    final_submission_status = FormStatus.succeeded
                    final_current_step = InitStep.complete
                    final_detail = "项目创建、工作空间初始化和欢迎消息已全部完成"
                    self._upsert_step(
                        submission_steps,
                        InitStep.complete,
                        status="success",
                        detail=final_detail,
                    )
                else:
                    if ws_status == WorkspaceStatus.partial_failed:
                        final_submission_status = "partial_failed"
                        final_current_step = "创建部分完成"
                        final_detail = "项目已可用，但仍有部分初始化步骤未完成"
                    elif ws_status == WorkspaceStatus.succeeded:
                        final_submission_status = "partial_failed"
                        final_current_step = "欢迎消息发送失败"
                        final_detail = welcome_step["detail"]
                    else:
                        final_submission_status = FormStatus.failed
                        final_current_step = "工作空间初始化失败"
                        final_detail = "项目创建未完整完成，请检查失败步骤"
                    self._upsert_step(
                        submission_steps,
                        InitStep.complete,
                        status="failure",
                        detail=final_detail,
                    )

                await self._sync_submission_card(
                    session,
                    submission_repo,
                    submission,
                    status=final_submission_status,
                    current_step=(final_current_step),
                    steps=submission_steps,
                    project_id=project.id,
                    error_message=None
                    if final_submission_status == FormStatus.succeeded
                    else final_detail,
                )

    async def _execute_agent_channel(
        self,
        project,
        *,
        on_step: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        """Run the workspace_init skill through the Agent Executor.

        Returns a dict with steps, chat_id, doc_url, group_link, agent_success.
        """
        task = registry.build_task(
            description="Initialize Feishu workspace for project",
            context={
                "project_name": project.name,
                "admin_open_id": project.admin_open_id,
                "git_repo_path": project.git_repo_path or "仓库待关联",
            },
            skill_name="workspace_init",
            complexity="smart",
            max_iterations=self.max_iterations,
        )
        agent_result = await self.agent_executor.execute(task)

        # First try to parse structured JSON from the agent's summary
        json_result = _try_parse_agent_json(agent_result.summary)
        if json_result:
            steps = json_result.get("steps", [])
            for step in steps:
                if on_step:
                    await on_step(step)
            return {
                "steps": steps,
                "chat_id": json_result.get("chat_id"),
                "doc_url": json_result.get("doc_url"),
                "document_id": json_result.get("document_id"),
                "group_link": json_result.get("group_link"),
                "agent_success": agent_result.success,
            }

        # Fallback: parse individual tool actions
        chat_id: str | None = None
        doc_url: str | None = None
        document_id: str | None = None
        group_link: str | None = None

        async def record_step(step: dict) -> None:
            steps.append(step)
            if on_step:
                await on_step(step)

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
                    await record_step(
                        {
                            "name": InitStep.create_chat,
                            "status": "success",
                            "detail": f"群ID: {chat_id}",
                        }
                    )
                else:
                    await record_step(
                        {
                            "name": InitStep.create_chat,
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

            elif tool_name == "im.v1.chat.members.create":
                if success:
                    await record_step(
                        {
                            "name": InitStep.add_admin,
                            "status": "success",
                            "detail": "管理员已加入",
                        }
                    )
                else:
                    await record_step(
                        {
                            "name": InitStep.add_admin,
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

            elif tool_name == "im.v1.chat.link":
                if success:
                    group_link = result_data.get("share_link")
                    await record_step(
                        {
                            "name": InitStep.get_chat_link,
                            "status": "success",
                            "detail": group_link or "已获取",
                        }
                    )
                else:
                    await record_step(
                        {
                            "name": InitStep.get_chat_link,
                            "status": "failure",
                            "detail": error or "无法获取",
                        }
                    )

            elif tool_name == "docx.v1.document.create":
                if success:
                    doc_url = result_data.get("url")
                    document_id = result_data.get("document_id")
                    await record_step(
                        {
                            "name": InitStep.create_doc,
                            "status": "success",
                            "detail": doc_url or "已创建",
                        }
                    )
                else:
                    await record_step(
                        {
                            "name": InitStep.create_doc,
                            "status": "failure",
                            "detail": error or "未知错误",
                        }
                    )

        if not agent_result.success and not steps:
            await record_step(
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
            "document_id": document_id,
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
        on_step: Callable[[dict], Awaitable[None]] | None = None,
    ) -> dict:
        """Direct SDK calls as a fallback when the Agent channel fails.

        Skips steps for which the resource already exists.
        """
        from teamflow.ai.tools.feishu import (
            _add_members_to_chat,
            _create_chat,
            _create_document,
            _get_chat_link,
        )

        steps: list[dict] = []
        document_id = self._extract_doc_token(doc_url)

        async def record_step(step: dict) -> None:
            steps.append(step)
            if on_step:
                await on_step(step)

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
                await record_step(
                    {
                        "name": InitStep.create_chat,
                        "status": "success",
                        "detail": f"群ID: {chat_id}",
                    }
                )
            except Exception as e:
                logger.exception("创建项目群失败")
                await record_step(
                    {"name": InitStep.create_chat, "status": "failure", "detail": str(e)}
                )

        # Step 2: Add admin
        if chat_id and project.admin_open_id:
            try:
                await _add_members_to_chat(chat_id, [project.admin_open_id])
                await record_step(
                    {
                        "name": InitStep.add_admin,
                        "status": "success",
                        "detail": "管理员已加入",
                    }
                )
            except Exception as e:
                logger.exception("添加管理员入群失败")
                await record_step(
                    {
                        "name": InitStep.add_admin,
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        # Step 3: Get chat link
        if chat_id and not group_link:
            try:
                result = await _get_chat_link(chat_id)
                group_link = result.get("share_link")
                await record_step(
                    {
                        "name": InitStep.get_chat_link,
                        "status": "success",
                        "detail": group_link or "已获取",
                    }
                )
            except Exception as e:
                logger.warning("获取群链接失败: %s", e)
                await record_step(
                    {
                        "name": InitStep.get_chat_link,
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        # Step 4: Create document
        if not doc_url:
            try:
                result = await _create_document(title=f"{project.name} - 项目文档")
                doc_url = result.get("url")
                document_id = result.get("document_id")
                await record_step(
                    {
                        "name": InitStep.create_doc,
                        "status": "success",
                        "detail": doc_url or "已创建",
                    }
                )
            except Exception as e:
                logger.exception("创建项目文档失败")
                await record_step(
                    {
                        "name": InitStep.create_doc,
                        "status": "failure",
                        "detail": str(e),
                    }
                )

        return {
            "steps": steps,
            "chat_id": chat_id,
            "doc_url": doc_url,
            "document_id": document_id,
            "group_link": group_link,
        }

    def _load_submission_steps(self, submission) -> list[dict]:
        try:
            steps = json.loads(submission.steps_payload)
        except json.JSONDecodeError:
            logger.warning("无效的提交步骤数据: %s", submission.request_id)
            return []
        return steps if isinstance(steps, list) else []

    def _upsert_step(self, steps: list[dict], name: str, *, status: str, detail: str) -> None:
        for step in steps:
            if step.get("name") == name:
                step["status"] = status
                step["detail"] = detail
                return
        steps.append({"name": name, "status": status, "detail": detail})

    def _extract_doc_token(self, doc_url: str | None) -> str | None:
        if not doc_url:
            return None
        parts = doc_url.rstrip("/").split("/docx/")
        if len(parts) != 2 or not parts[1]:
            return None
        return parts[1].split("?")[0]

    async def _ensure_document_owner(
        self,
        *,
        document_id: str,
        admin_open_id: str,
        report_step: Callable[[dict], Awaitable[None]],
    ) -> bool:
        from teamflow.ai.tools.feishu import (
            _add_document_collaborator,
            _transfer_document_owner,
        )

        try:
            await _add_document_collaborator(document_id, admin_open_id)
            await _transfer_document_owner(document_id, admin_open_id)
            await report_step(
                {
                    "name": InitStep.transfer_owner,
                    "status": "success",
                    "detail": "文档所有者已转交给项目管理员",
                }
            )
            return True
        except Exception as exc:
            logger.warning("转交文档所有者失败: %s", exc)
            await report_step(
                {
                    "name": InitStep.transfer_owner,
                    "status": "failure",
                    "detail": str(exc),
                }
            )
            return False

    async def _sync_submission_card(
        self,
        session,
        submission_repo: ProjectFormSubmissionRepo,
        submission,
        *,
        status: str,
        current_step: str,
        steps: list[dict],
        project_id: str,
        error_message: str | None = None,
    ) -> None:
        updated = submission_repo.update_progress(
            submission.request_id,
            status=status,
            current_step=current_step,
            steps=steps,
            project_id=project_id,
            error_message=error_message,
        )
        session.commit()
        if not updated:
            return

        card = project_create_status_card(
            status=updated.status,
            project_name=updated.project_name,
            git_repo_path=updated.git_repo_path,
            steps=steps,
            current_step=updated.current_step,
            project_id=updated.project_id,
            error_message=updated.error_message,
        )
        result = await update_card_message_async(
            self.feishu,
            updated.open_message_id,
            card,
        )
        if not result.success:
            logger.warning("更新提交卡片失败: %s", result.error)

    async def _send_group_welcome(
        self,
        project_name: str,
        *,
        chat_id: str | None,
        doc_url: str | None,
    ) -> dict | None:
        if not chat_id:
            return {
                "name": InitStep.send_welcome,
                "status": "skipped",
                "detail": "项目群不存在，跳过欢迎消息发送",
            }

        try:
            welcome = await send_card_async(
                self.feishu,
                workspace_welcome_card(project_name, doc_url),
                chat_id=chat_id,
            )
            if not welcome.success:
                logger.warning("欢迎卡片发送失败，尝试文本: %s", welcome.error)
                txt = f"欢迎来到 {project_name} 项目！\n这是 TeamFlow AI 协作空间。"
                if doc_url:
                    txt += f"\n项目文档: {doc_url}"
                fallback = await send_text_async(self.feishu, txt, chat_id=chat_id)
                if not fallback.success:
                    return {
                        "name": InitStep.send_welcome,
                        "status": "failure",
                        "detail": fallback.error or "欢迎消息发送失败",
                    }
                return {
                    "name": InitStep.send_welcome,
                    "status": "success",
                    "detail": "卡片发送失败，已降级为文本消息",
                }
            return {
                "name": InitStep.send_welcome,
                "status": "success",
                "detail": "已发送",
            }
        except Exception as exc:
            logger.exception("发送群欢迎消息失败")
            return {
                "name": InitStep.send_welcome,
                "status": "failure",
                "detail": str(exc),
            }

r"""端到端业务流程测试。

用法:
  PYTHONIOENCODING=utf-8 python scripts/e2e_test.py

覆盖范围:
  1. 发送创建项目表单卡片到飞书
  2. 自动模拟一次真实表单提交
  3. 触发项目创建 + Gitea 自动创建仓库 + 工作空间初始化 + 欢迎消息发送
  4. 等待同一张进度卡走到最终状态
  5. 输出结果并自动清理本次创建的飞书资源、Gitea 仓库与数据库记录
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 240


@dataclass
class RunContext:
    request_id: str
    project_name: str
    git_repo_path: str | None
    user_id: str
    chat_id: str = ""
    form_message_id: str = ""
    project_id: str = ""
    workspace_chat_id: str = ""
    workspace_doc_url: str = ""
    workspace_doc_owner_id: str = ""
    summary_message_id: str = ""
    final_submission_status: str = ""
    final_current_step: str = ""
    gitea_repo_url: str = ""
    gitea_repo_full_name: str = ""
    gitea_auto_created: bool = False
    cleanup_errors: list[str] | None = None


def banner(text: str):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def ok(text: str):
    print(f"  [OK] {text}")


def fail(text: str):
    print(f"  [FAIL] {text}")


def info(text: str):
    print(f"  [..] {text}")


def _new_run_context(user_id: str, *, skip_repo: bool = False) -> RunContext:
    """生成一组随机 mock 数据，避免污染真实项目。

    Args:
        skip_repo: 为 True 时不填仓库地址，触发 Gitea 自动创建。
    """
    suffix = uuid.uuid4().hex[:8]
    return RunContext(
        request_id=f"e2e-{uuid.uuid4()}",
        project_name=f"TeamFlow-E2E-{suffix}",
        git_repo_path=None if skip_repo else f"https://github.com/mock-org/teamflow-e2e-{suffix}.git",
        user_id=user_id,
        cleanup_errors=[],
    )


def _extract_field(payload: dict | None, *keys: str) -> str:
    """从可能嵌套的发送结果中提取字段。"""
    if not isinstance(payload, dict):
        return ""

    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)

    return current if isinstance(current, str) else ""


def _extract_message_context(payload: dict | None) -> tuple[str, str]:
    """提取消息 ID 和 chat_id，兼容不同的返回结构。"""
    message_id = (
        _extract_field(payload, "message_id")
        or _extract_field(payload, "data", "message_id")
        or _extract_field(payload, "raw", "message_id")
    )
    chat_id = (
        _extract_field(payload, "chat_id")
        or _extract_field(payload, "data", "chat_id")
        or _extract_field(payload, "raw", "chat_id")
    )
    return message_id, chat_id


def _extract_doc_token(doc_url: str) -> str:
    """从 docx URL 中提取文档 token。"""
    if not doc_url:
        return ""
    path = urlparse(doc_url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] == "docx":
        return parts[1]
    return ""


def _load_dotenv():
    """加载项目根目录的 .env 文件到 os.environ。"""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.is_file():
        import os

        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() and key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()
                    info(f"加载 .env: {key.strip()}=***")


def _build_lark_client(feishu):
    """创建独立的飞书 SDK 客户端，用于清理阶段。"""
    import lark_oapi as lark

    base_url = (
        "https://open.feishu.cn" if feishu.brand == "feishu" else "https://open.larksuite.com"
    )
    return (
        lark.Client.builder()
        .app_id(feishu.app_id)
        .app_secret(feishu.app_secret)
        .domain(base_url)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )


def _list_accessible_doc_owners(feishu) -> dict[str, str]:
    """递归列出 bot 当前可见 docx 的 owner_id。"""
    import lark_oapi as lark

    client = _build_lark_client(feishu)
    owners: dict[str, str] = {}
    pending_folders = [""]
    visited_folders = {""}

    while pending_folders:
        folder_token = pending_folders.pop(0)
        page_token = ""

        while True:
            builder = (
                lark.drive.v1.ListFileRequest.builder()
                .page_size(200)
                .order_by("EditedTime")
                .direction("DESC")
            )
            if folder_token:
                builder = builder.folder_token(folder_token)
            if page_token:
                builder = builder.page_token(page_token)

            req = builder.build()
            resp = client.drive.v1.file.list(req)
            if not resp.success():
                raise RuntimeError(f"列出文档失败: {resp.msg} ({resp.code})")

            data = resp.data
            files = data.files if data and data.files else []
            for file in files:
                if not file.token:
                    continue
                if file.type == "folder":
                    if file.token not in visited_folders:
                        visited_folders.add(file.token)
                        pending_folders.append(file.token)
                    continue
                if file.type != "docx":
                    continue
                owners[file.token] = file.owner_id or ""

            if not data or not data.has_more or not data.next_page_token:
                break
            page_token = data.next_page_token

    return owners


def _get_doc_owner_id(feishu, doc_url: str) -> str:
    """查询当前文档的 owner_id。"""
    doc_token = _extract_doc_token(doc_url)
    if not doc_token:
        return ""
    owners = _list_accessible_doc_owners(feishu)
    return owners.get(doc_token, "")


async def _delete_message(feishu, message_id: str) -> None:
    """删除脚本发送的消息卡片，避免聊天里残留测试内容。"""
    if not message_id:
        return

    import lark_oapi as lark

    client = _build_lark_client(feishu)
    req = lark.im.v1.DeleteMessageRequest.builder().message_id(message_id).build()
    resp = await asyncio.to_thread(client.im.v1.message.delete, req)
    if not resp.success():
        raise RuntimeError(f"删除消息失败: {resp.msg} ({resp.code})")


async def _delete_chat(feishu, chat_id: str) -> None:
    """解散本次 E2E 创建的项目群。"""
    if not chat_id:
        return

    import lark_oapi as lark

    client = _build_lark_client(feishu)
    req = lark.im.v1.DeleteChatRequest.builder().chat_id(chat_id).build()
    resp = await asyncio.to_thread(client.im.v1.chat.delete, req)
    if not resp.success():
        raise RuntimeError(f"删除群组失败: {resp.msg} ({resp.code})")


async def _delete_doc(feishu, doc_url: str) -> None:
    """删除本次 E2E 创建的项目文档。"""
    doc_token = _extract_doc_token(doc_url)
    if not doc_token:
        return

    import lark_oapi as lark

    client = _build_lark_client(feishu)
    req = lark.drive.v1.DeleteFileRequest.builder().file_token(doc_token).type("docx").build()
    resp = await asyncio.to_thread(client.drive.v1.file.delete, req)
    if not resp.success():
        raise RuntimeError(f"删除文档失败: {resp.msg} ({resp.code})")


def _cleanup_database(get_session, request_id: str, project_id: str) -> None:
    """删除本次 E2E 产生的数据库记录。"""
    from sqlmodel import select

    from teamflow.storage.models import ActionLog, EventLog, Project, ProjectFormSubmission

    with get_session() as session:
        submission = session.exec(
            select(ProjectFormSubmission).where(ProjectFormSubmission.request_id == request_id)
        ).first()
        if submission:
            session.delete(submission)

        if project_id:
            action_logs = session.exec(
                select(ActionLog).where(ActionLog.project_id == project_id)
            ).all()
            for row in action_logs:
                session.delete(row)

            event_logs = session.exec(
                select(EventLog).where(EventLog.project_id == project_id)
            ).all()
            for row in event_logs:
                session.delete(row)

            project = session.get(Project, project_id)
            if project:
                session.delete(project)

        session.commit()


async def _delete_gitea_repo(gitea_config, repo_full_name: str) -> None:
    """删除 Gitea 上本次 E2E 自动创建的仓库。"""
    if not repo_full_name or not gitea_config.base_url or not gitea_config.access_token:
        return

    from teamflow.config.settings import GiteaConfig
    from teamflow.git.gitea_service import GiteaService

    svc = GiteaService(gitea_config)
    await svc.delete_repo(repo_full_name)
    await svc.close()


async def _cleanup_run(feishu, get_session, ctx: RunContext, gitea_config=None) -> None:
    """按最佳努力顺序回收飞书资源、Gitea 仓库和数据库记录。"""
    errors = ctx.cleanup_errors if ctx.cleanup_errors is not None else []

    if ctx.gitea_auto_created and gitea_config:
        try:
            await _delete_gitea_repo(gitea_config, ctx.gitea_repo_full_name)
            ok("已删除 Gitea 测试仓库")
        except Exception as exc:
            errors.append(f"删除 Gitea 仓库失败: {exc}")
            fail(errors[-1])

    try:
        await _delete_message(feishu, ctx.form_message_id)
        ok("已删除创建进度卡")
    except Exception as exc:
        errors.append(f"删除进度卡失败: {exc}")
        fail(errors[-1])

    try:
        await _delete_chat(feishu, ctx.workspace_chat_id)
        ok("已删除项目群")
    except Exception as exc:
        errors.append(f"删除项目群失败: {exc}")
        fail(errors[-1])

    try:
        ctx.workspace_doc_owner_id = (
            _get_doc_owner_id(feishu, ctx.workspace_doc_url) or ctx.workspace_doc_owner_id
        )
    except Exception as exc:
        errors.append(f"查询文档 owner 失败: {exc}")
        fail(errors[-1])

    try:
        await _delete_doc(feishu, ctx.workspace_doc_url)
        ok("已删除项目文档")
    except Exception as exc:
        if ctx.workspace_doc_owner_id and ctx.workspace_doc_owner_id != ctx.user_id:
            errors.append(
                f"删除项目文档失败: {exc}；当前 owner_id={ctx.workspace_doc_owner_id}，不是管理员 open_id"
            )
        elif ctx.workspace_doc_owner_id == ctx.user_id:
            errors.append(
                f"删除项目文档失败: {exc}；当前 owner 已是管理员 {ctx.workspace_doc_owner_id}，bot 无删除权限"
            )
        else:
            errors.append(f"删除项目文档失败: {exc}")
        fail(errors[-1])

    try:
        await asyncio.to_thread(_cleanup_database, get_session, ctx.request_id, ctx.project_id)
        ok("已删除数据库记录")
    except Exception as exc:
        errors.append(f"删除数据库记录失败: {exc}")
        fail(errors[-1])


async def _wait_for_completion(get_session, ctx: RunContext) -> None:
    """等待表单提交记录进入最终状态，并同步项目资源信息。"""
    from sqlmodel import select

    from teamflow.storage.models import Project, ProjectFormSubmission

    waited = 0
    last_step = ""
    while waited < MAX_WAIT_SECONDS:
        with get_session() as session:
            submission = session.exec(
                select(ProjectFormSubmission).where(
                    ProjectFormSubmission.request_id == ctx.request_id
                )
            ).first()
            if submission:
                ctx.project_id = submission.project_id or ctx.project_id
                ctx.final_submission_status = submission.status
                ctx.final_current_step = submission.current_step
                if submission.current_step != last_step:
                    info(f"当前步骤: {submission.current_step} [{submission.status}]")
                    last_step = submission.current_step

            if ctx.project_id:
                project = session.get(Project, ctx.project_id)
                if project:
                    ctx.workspace_chat_id = project.feishu_group_id or ctx.workspace_chat_id
                    ctx.workspace_doc_url = project.feishu_doc_url or ctx.workspace_doc_url
                    if project.git_repo_path and project.git_repo_auto_created:
                        ctx.gitea_repo_url = project.git_repo_path
                        ctx.gitea_auto_created = True

            if submission and submission.status in ("succeeded", "partial_failed", "failed"):
                info(
                    f"流程已收口: submission={submission.status}, "
                    f"current_step={submission.current_step} (等待 {waited}s)"
                )
                return

        dots = "." * ((waited // POLL_INTERVAL_SECONDS) % 4 + 1)
        print(f"\r  等待中{dots}   ", end="", flush=True)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS

    print()
    raise TimeoutError("等待超时，完整流程可能仍在后台运行")


def _print_run_snapshot(feishu, get_session, ctx: RunContext) -> None:
    """输出本次运行对应的项目和提交记录。"""
    from sqlmodel import select

    from teamflow.storage.models import ActionLog, EventLog, Project, ProjectFormSubmission

    with get_session() as session:
        submission = session.exec(
            select(ProjectFormSubmission).where(ProjectFormSubmission.request_id == ctx.request_id)
        ).first()
        project = session.get(Project, ctx.project_id) if ctx.project_id else None

        if project:
            try:
                ctx.workspace_doc_owner_id = (
                    _get_doc_owner_id(
                        feishu,
                        project.feishu_doc_url or "",
                    )
                    or ctx.workspace_doc_owner_id
                )
            except Exception:
                pass
            print(f"  项目: {project.name}")
            print(f"    id:               {project.id}")
            print(f"    status:           {project.status}")
            print(f"    workspace:        {project.workspace_status}")
            print(f"    group_id:         {project.feishu_group_id or '—'}")
            print(f"    doc_url:          {project.feishu_doc_url or '—'}")
            print(f"    doc_owner:        {ctx.workspace_doc_owner_id or '—'}")
            print(f"    link:             {project.feishu_group_link or '—'}")
            print(f"    git_repo_path:    {project.git_repo_path or '—'}")
            print(f"    git_repo_platform:{project.git_repo_platform or '—'}")
            print(f"    git_auto_created: {project.git_repo_auto_created}")
            print()
        else:
            fail("数据库中未找到本次项目记录")

        if submission:
            print("  提交记录:")
            print(f"    request_id: {submission.request_id}")
            print(f"    status:     {submission.status}")
            print(f"    step:       {submission.current_step}")
            print(f"    project_id: {submission.project_id or '—'}")
            print(f"    error:      {submission.error_message or '—'}")
            print()
        else:
            fail("数据库中未找到本次表单提交记录")

        if ctx.project_id:
            action_count = len(
                session.exec(select(ActionLog).where(ActionLog.project_id == ctx.project_id)).all()
            )
            event_count = len(
                session.exec(select(EventLog).where(EventLog.project_id == ctx.project_id)).all()
            )
            print("  关联记录:")
            print(f"    action_logs: {action_count}")
            print(f"    event_logs:  {event_count}")
            print()


async def main():
    # ====================================================================
    # Step 0: 加载 .env
    # ====================================================================
    _load_dotenv()

    # ====================================================================
    # Step 1: 加载配置
    # ====================================================================
    banner("Step 1: 加载配置")

    from teamflow.config import load_config

    config = load_config()
    feishu = config.feishu

    info(f"app_id: {feishu.app_id[:8]}...")
    info(f"admin_open_id: {feishu.admin_open_id or '(not set)'}")
    info(f"smart_model: {config.agent.smart_model}")

    if not feishu.app_id or not feishu.app_secret:
        fail("飞书配置不完整，请先运行 teamflow setup")
        return

    if not feishu.admin_open_id:
        fail("未配置 admin_open_id。请在 config.yaml 中设置后重试")
        return

    user_id = feishu.admin_open_id

    gitea_config = config.gitea
    gitea_available = bool(gitea_config.base_url and gitea_config.access_token)
    if gitea_available:
        info(f"gitea: {gitea_config.base_url} (auto_create={gitea_config.auto_create})")
    else:
        info("gitea: 未配置，跳过自动创建仓库测试")

    ctx = _new_run_context(user_id, skip_repo=gitea_available)
    ok("配置加载成功")
    info(f"mock 项目名: {ctx.project_name}")
    info(f"mock 仓库: {ctx.git_repo_path or '(留空，触发 Gitea 自动创建)'}")

    # ====================================================================
    # Step 2: 初始化
    # ====================================================================
    banner("Step 2: 初始化")

    from teamflow.storage.database import get_session, init_db

    init_db()
    ok("数据库初始化完成")

    from teamflow.ai.agent import AgentExecutor
    from teamflow.ai.tools.feishu import init_feishu_client

    try:
        init_feishu_client(
            app_id=feishu.app_id,
            app_secret=feishu.app_secret,
            brand=feishu.brand,
        )
        ok("飞书 SDK 初始化成功")
    except Exception as e:
        fail(f"飞书 SDK 初始化失败: {e}")
        return

    from teamflow.ai import tool_provider as tp

    agent = AgentExecutor(
        tp,
        model_overrides={
            "fast": config.agent.fast_model,
            "smart": config.agent.smart_model,
            "reasoning": config.agent.reasoning_model,
        },
        provider=config.agent.provider,
        timeout_seconds=config.agent.timeout_seconds,
    )
    ok(f"Agent 就绪 ({len(tp.tools)} tools)")

    if not agent.validate_model("smart"):
        fail("smart_model 可能不支持 tool calling，Agent 调用会失败")

    # ====================================================================
    # Step 3: 发送表单卡片
    # ====================================================================
    banner("Step 3: 发送表单卡片")

    from teamflow.execution.messages import send_card
    from teamflow.orchestration.card_templates import project_create_form_card

    result = send_card(feishu, project_create_form_card(request_id=ctx.request_id), user_id=user_id)
    if not result.success:
        fail(f"发送失败: {result.error}")
        return

    ctx.form_message_id, ctx.chat_id = _extract_message_context(result.output)
    ok("表单卡片已发送，准备自动模拟提交")
    info(f"request_id: {ctx.request_id}")
    info(f"message_id: {ctx.form_message_id or '(not returned)'}")
    info(f"chat_id: {ctx.chat_id or '(not returned)'}")

    if not ctx.form_message_id or not ctx.chat_id:
        fail("发送表单卡后未拿到 message_id 或 chat_id，无法继续自动化流程")
        return

    try:
        # ====================================================================
        # Step 4: 模拟提交
        # ====================================================================
        banner("Step 4: 自动模拟提交")

        from teamflow.access.parser import CardActionData
        from teamflow.orchestration.event_bus import EventBus
        from teamflow.orchestration.project_flow import ProjectCreateFlow
        from teamflow.orchestration.workspace_flow import WorkspaceInitFlow

        workspace_flow = WorkspaceInitFlow(
            feishu=feishu,
            agent_executor=agent,
            session_factory=get_session,
            max_iterations=config.agent.max_iterations,
        )
        EventBus.subscribe_global("project.created", workspace_flow.on_project_created)
        ok("Workspace init handler 已注册到全局事件总线")

        await asyncio.sleep(1)

        with get_session() as session:
            event_bus = EventBus(session)
            flow = ProjectCreateFlow(feishu, session, event_bus, gitea_config)
            form_values = {
                "project_name": ctx.project_name,
            }
            if ctx.git_repo_path:
                form_values["git_repo_path"] = ctx.git_repo_path
            card_data = CardActionData(
                open_id=user_id,
                chat_id=ctx.chat_id,
                open_message_id=ctx.form_message_id,
                action_tag="button",
                action_value={
                    "teamflow_action": "submit_project_form",
                    "request_id": ctx.request_id,
                },
                form_values=form_values,
                token=f"e2e-token-{ctx.request_id}",
            )
            submit_result = flow.submit_form(card_data)
            ok(f"表单提交已受理: {submit_result.toast_text}")

        # ====================================================================
        # Step 5: 等待完整流程结束
        # ====================================================================
        banner("Step 5: 等待完整流程")
        info("后台正在执行项目创建、工作空间初始化和欢迎消息发送...")
        await _wait_for_completion(get_session, ctx)
        print()

        # ====================================================================
        # Step 6: 输出结果
        # ====================================================================
        banner("Step 6: 输出结果")
        _print_run_snapshot(feishu, get_session, ctx)

        # 从 Gitea repo URL 提取 full_name 用于清理
        if ctx.gitea_auto_created and ctx.gitea_repo_url:
            from urllib.parse import urlparse

            parsed = urlparse(ctx.gitea_repo_url)
            path = parsed.path.strip("/")
            if path.endswith(".git"):
                path = path[:-4]
            ctx.gitea_repo_full_name = path
            info(f"Gitea 仓库 full_name: {ctx.gitea_repo_full_name}")

    finally:
        # ====================================================================
        # Step 7: 清理资源
        # ====================================================================
        banner("Step 7: 清理资源")
        await _cleanup_run(feishu, get_session, ctx, gitea_config)

    print(f"\n{'=' * 60}")
    print("  E2E 测试总结")
    print(f"{'=' * 60}")
    print()

    checks: list[tuple[str, bool, str]] = []

    checks.append(("配置加载", bool(feishu.app_id and feishu.app_secret), "飞书 app_id/app_secret 已配置"))
    checks.append(("数据库初始化", True, "SQLite 初始化成功"))

    project_ok = ctx.final_submission_status in ("succeeded", "partial_failed")
    checks.append(("项目创建", project_ok, f"最终状态: {ctx.final_submission_status or 'unknown'}"))

    checks.append(("工作空间初始化", bool(ctx.workspace_chat_id), f"群: {ctx.workspace_chat_id or '—'}"))
    checks.append(("项目文档创建", bool(ctx.workspace_doc_url), f"文档: {ctx.workspace_doc_url or '—'}"))

    if gitea_available:
        checks.append(("Gitea 自动创建仓库", ctx.gitea_auto_created, f"仓库: {ctx.gitea_repo_url or '—'}"))
    else:
        checks.append(("Gitea 自动创建仓库", True, "未配置，已跳过"))

    cleanup_ok = not ctx.cleanup_errors
    checks.append(("资源清理", cleanup_ok, "全部完成" if cleanup_ok else f"{len(ctx.cleanup_errors)} 项失败"))

    pass_count = sum(1 for _, ok_flag, _ in checks if ok_flag)
    fail_count = len(checks) - pass_count

    for name, ok_flag, detail in checks:
        mark = "✓" if ok_flag else "✗"
        print(f"  [{mark}] {name}: {detail}")
    print()

    if fail_count == 0:
        print(f"  全部通过 ({pass_count}/{len(checks)})")
    else:
        print(f"  {fail_count} 项失败，{pass_count} 项通过 ({pass_count}/{len(checks)})")
        if ctx.cleanup_errors:
            print()
            print("  清理失败详情:")
            for item in ctx.cleanup_errors:
                print(f"    - {item}")

    print()
    print(f"  request_id: {ctx.request_id}")
    print(f"  project_id: {ctx.project_id or '—'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())

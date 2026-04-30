r"""端到端业务流程测试 — 模拟用户在飞书里创建项目的完整过程。

用法:
  PYTHONIOENCODING=utf-8 python scripts/e2e_test.py

步骤:
  1. 发送表单卡片到飞书（等待填写）
  2. 确认后自动模拟提交表单 → 创建项目
  3. 触发工作空间初始化（Agent + LLM + 飞书 API）
  4. 检查数据库结果
  5. 发送测试摘要到飞书
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


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
    ok("配置加载成功")

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

    result = send_card(feishu, project_create_form_card(), user_id=user_id)
    if result.success:
        ok("表单卡片已发送！请在飞书中查看并填写表单，然后回到终端按 Y 继续")
    else:
        fail(f"发送失败: {result.error}")
        return

    # ====================================================================
    # Step 4: 等待确认后执行项目创建
    # ====================================================================
    banner("Step 4: 等待确认")

    try:
        ans = input("  确认执行项目创建？[Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"
    if ans in ("n", "no"):
        info("已取消。")
        return

    project_name = "E2E测试项目"
    git_repo_path = "https://github.com/teamflow/test-project"

    banner("Step 5: 执行项目创建")

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

    with get_session() as session:
        event_bus = EventBus(session)
        flow = ProjectCreateFlow(feishu, session, event_bus)
        flow.create_from_form(user_id, user_id, {
            "project_name": project_name,
            "git_repo_path": git_repo_path,
        })

    ok(f"项目已创建: {project_name}")
    info("Agent 正在执行工作空间初始化（LLM 调用 + 飞书 API，约 30-60 秒）...")

    # 轮询等待 workspace init 异步任务完成
    from sqlmodel import select as sq_select

    from teamflow.storage.models import Project as Pm
    waited = 0
    while waited < 120:
        with get_session() as s:
            latest = s.exec(
                sq_select(Pm).where(Pm.name == project_name)
                .order_by(Pm.created_at.desc())
            ).first()
            if latest and latest.workspace_status in ("succeeded", "partial_failed", "failed"):
                info(f"工作空间初始化完成: {latest.workspace_status} (等待 {waited}s)")
                break
        dots = "." * ((waited // 5) % 4 + 1)
        print(f"\r  等待中{dots}   ", end="", flush=True)
        await asyncio.sleep(5)
        waited += 5
    else:
        info("等待超时，Agent 可能仍在运行")
    print()

    # ====================================================================
    # Step 6: 检查结果
    # ====================================================================
    banner("Step 6: 数据库结果")

    from sqlmodel import select

    from teamflow.storage.models import Project

    with get_session() as session:
        projects = session.exec(
            select(Project).order_by(Project.created_at.desc()).limit(3)
        ).all()

        if projects:
            for p in projects:
                print(f"  项目: {p.name}")
                print(f"    status: {p.status}")
                print(f"    workspace: {p.workspace_status}")
                print(f"    group_id: {p.feishu_group_id or '—'}")
                print(f"    doc_url:  {p.feishu_doc_url or '—'}")
                print(f"    link:     {p.feishu_group_link or '—'}")
                print()
        else:
            fail("数据库中未找到任何项目")

    # ====================================================================
    # Step 7: 发送测试摘要
    # ====================================================================
    banner("Step 7: 发送测试摘要")

    from teamflow.execution.messages import send_text

    summary = (
        "TeamFlow E2E 测试完成\n\n"
        f"项目名称: {project_name}\n"
        f"仓库地址: {git_repo_path}\n\n"
        "请在飞书中检查：\n"
        "1. 是否收到了项目创建成功的卡片\n"
        "2. 是否收到了工作空间初始化的回执\n"
        "3. 是否被拉入了项目群\n"
        "4. 项目文档是否已创建"
    )

    result = send_text(feishu, summary, user_id=user_id)
    if result.success:
        ok("测试摘要已发送到飞书，请查看")
    else:
        fail(f"摘要发送失败: {result.error}")

    print(f"\n{'=' * 60}")
    print("  E2E 测试流程完成！")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())

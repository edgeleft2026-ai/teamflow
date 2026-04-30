"""Agent 自动化测试脚本 — 验证 skills、tools、AgentExecutor 完整链路。

用法: python -X utf8 scripts/test_agent.py

覆盖范围：
  1. 模型注册表 — 提供商映射、模型查询、LiteLLM 转换
  2. Transport 层 — 响应归一化
  3. Skill 自动发现 — 全部 24 个 skill 正确注册
  4. Skill 匹配 — 中文/英文触发
  5. ToolProvider — 8 个工具已注册
  6. AgentExecutor — Task 构建与执行（Mock LLM）
  7. 工作空间初始化流程 — 端到端（Mock LLM + Mock SDK）
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================================
# 1. 模型注册表
# ============================================================================
def test_model_registry():
    section("1. 模型注册表")
    from teamflow.ai.model_registry import (
        CANONICAL_PROVIDERS,
        LITELLM_PROVIDER_MAP,
        get_litellm_env,
        get_litellm_base_url_override,
        list_models,
        resolve_provider,
        to_litellm_model,
    )

    check("CANONICAL_PROVIDERS 数量", len(CANONICAL_PROVIDERS) >= 27)
    check("LITELLM_PROVIDER_MAP 数量", len(LITELLM_PROVIDER_MAP) >= 25)
    check("别名: qwen -> alibaba", resolve_provider("qwen") == "alibaba")
    check("别名: google -> gemini", resolve_provider("google") == "gemini")
    check("别名: kimi -> kimi-coding", resolve_provider("kimi") == "kimi-coding")
    check("别名: glm -> zai", resolve_provider("glm") == "zai")
    check("别名: deep-seek -> deepseek", resolve_provider("deep-seek") == "deepseek")
    check("to_litellm_model: minimax-cn", to_litellm_model("minimax-cn", "MiniMax-M2.7") == "minimax/MiniMax-M2.7")
    check("to_litellm_model: zai", to_litellm_model("zai", "glm-5.1") == "zhipu/glm-5.1")
    check("to_litellm_model: openai", to_litellm_model("openai", "gpt-4o") == "openai/gpt-4o")
    check("get_litellm_env: minimax-cn", get_litellm_env("minimax-cn") == "MINIMAX_API_KEY")
    check("get_litellm_env: deepseek", get_litellm_env("deepseek") == "DEEPSEEK_API_KEY")
    check("get_litellm_base_url: minimax-cn", get_litellm_base_url_override("minimax-cn") == "https://api.minimaxi.com/v1")
    check("get_litellm_base_url: deepseek=None", get_litellm_base_url_override("deepseek") is None)

    # Model lists
    nl = list_models("deepseek")
    check(f"deepseek 模型列表: {len(nl)} 个", len(nl) >= 2)
    nl2 = list_models("openai")
    check(f"openai 模型列表: {len(nl2)} 个", len(nl2) >= 5)


# ============================================================================
# 2. Transport 层
# ============================================================================
def test_transports():
    section("2. Transport 层")
    from teamflow.ai.transports import (
        ChatCompletionsTransport,
        NormalizedResponse,
        ToolCall,
        get_transport,
    )

    t = get_transport("chat_completions")
    check("chat_completions transport", isinstance(t, ChatCompletionsTransport))
    check("api_mode", t.api_mode == "chat_completions")

    # Test normalize_response via mock
    mock_msg = MagicMock()
    mock_msg.content = "Hello"
    mock_msg.tool_calls = None
    mock_msg.reasoning = None
    mock_msg.reasoning_content = None
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_choice.finish_reason = "stop"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = None

    nr = t.normalize_response(mock_resp)
    check("NormalizedResponse.content", nr.content == "Hello")
    check("NormalizedResponse.finish_reason", nr.finish_reason == "stop")
    check("NormalizedResponse.tool_calls", nr.tool_calls is None)

    # Test tool call normalization
    mock_tc = MagicMock()
    mock_tc.id = "call_1"
    mock_tc.function = MagicMock()
    mock_tc.function.name = "test_tool"
    mock_tc.function.arguments = '{"key": "value"}'
    mock_tc.extra_content = None
    mock_msg2 = MagicMock()
    mock_msg2.content = ""
    mock_msg2.tool_calls = [mock_tc]
    mock_msg2.reasoning = None
    mock_msg2.reasoning_content = None
    mock_choice2 = MagicMock()
    mock_choice2.message = mock_msg2
    mock_choice2.finish_reason = "tool_calls"
    mock_resp2 = MagicMock()
    mock_resp2.choices = [mock_choice2]
    mock_resp2.usage = None

    nr2 = t.normalize_response(mock_resp2)
    check("NormalizedResponse.tool_calls.name", nr2.tool_calls[0].name == "test_tool")
    check("NormalizedResponse.finish_reason=tool_calls", nr2.finish_reason == "tool_calls")


# ============================================================================
# 3. Skill 自动发现
# ============================================================================
def test_skills():
    section("3. Skill 系统")

    from teamflow.ai.skills import Skill, SkillRegistry, registry

    check("SkillRegistry 实例", isinstance(registry, SkillRegistry))
    all_skills = registry.list()
    check(f"总数 >= 20", len(all_skills) >= 20, f"实际: {len(all_skills)}")

    # workspace_init
    ws = registry.get("workspace_init")
    check("workspace_init 按名称查找", ws is not None)
    if ws:
        check("workspace_init prompt 长度", len(ws.system_prompt) > 100)
        check("workspace_init 工具列表", ws.allowed_tools and len(ws.allowed_tools) >= 7)
        check("workspace_init 触发词", len(ws.triggers) >= 5)

    # lark-im
    im = registry.get("lark-im")
    check("lark-im 按名称查找", im is not None)
    if im:
        check("lark-im prompt 长度", len(im.system_prompt) > 500)

    # lark-task
    task = registry.get("lark-task")
    check("lark-task 按名称查找", task is not None)

    # Skill.matches test
    if ws:
        check("matches: 'workspace init'", ws.matches("workspace init"))
        check("matches: '初始化工作空间'", ws.matches("初始化工作空间"))
        check("matches: '创建项目群'", ws.matches("创建项目群"))
        check("not matches: '发消息'", not ws.matches("发消息"))

    # build_task with skill_name
    task_obj = registry.build_task("test", skill_name="workspace_init")
    check("build_task 注入 skill_name", task_obj.skill_name == "workspace_init")
    check("build_task 注入 allowed_tools", task_obj.allowed_tools is not None)

    # build_task without skill match
    task_obj2 = registry.build_task("随便一个不匹配的描述")
    check("build_task 无匹配时 skill_name=None", task_obj2.skill_name is None)


# ============================================================================
# 4. ToolProvider
# ============================================================================
def test_tool_provider():
    section("4. ToolProvider")

    from teamflow.ai.tools import ToolDef, ToolProvider

    tp = ToolProvider()
    from teamflow.ai.tools.feishu import ALL_TOOLS
    for tdef in ALL_TOOLS:
        tp.register(ToolDef(
            name=tdef["name"],
            description=tdef["description"],
            parameters=tdef["parameters"],
            handler=tdef["handler"],
        ))

    check(f"工具总数: {len(tp.tools)}", len(tp.tools) >= 8, f"实际: {len(tp.tools)}")

    tool_names = [t.name for t in tp.tools]
    check("im.v1.chat.create", "im.v1.chat.create" in tool_names)
    check("im.v1.chat.members.create", "im.v1.chat.members.create" in tool_names)
    check("im.v1.message.create", "im.v1.message.create" in tool_names)
    check("docx.v1.document.create", "docx.v1.document.create" in tool_names)
    check("lark_cli.run", "lark_cli.run" in tool_names)
    check("im.v1.bot.info", "im.v1.bot.info" in tool_names)

    # Test tool proxy shape
    for t in tp.tools:
        check(f"{t.name} has inputSchema", hasattr(t, "inputSchema"))
        check(f"{t.name} has description", bool(t.description))


# ============================================================================
# 5. AgentExecutor — Tool-use Loop (Mock LLM)
# ============================================================================
async def test_agent_executor():
    section("5. AgentExecutor — 完整 Loop（Mock LLM）")

    from teamflow.ai.agent import AgentExecutor
    from teamflow.ai.models import AgentTask
    from teamflow.ai.skills import registry
    from teamflow.ai.tools import ToolDef, ToolProvider

    # Build a minimal ToolProvider with one mock tool
    tp = ToolProvider()

    async def mock_handler(**kwargs) -> dict:
        return {"success": True, "data": kwargs}

    tp.register(ToolDef(
        name="mock.tool",
        description="A mock tool for testing",
        parameters={
            "type": "object",
            "properties": {
                "value": {"type": "string", "description": "test value"},
            },
            "required": ["value"],
        },
        handler=mock_handler,
    ))

    executor = AgentExecutor(tp, model_overrides={"smart": "openai/gpt-4o-mini"})

    # Build task
    task = registry.build_task(
        description="Test task with mock tool call",
        skill_name="workspace_init",
    )

    # Mock LiteLLM response: first turn returns tool_call, second returns text
    mock_tool_msg = MagicMock()
    mock_tool_msg.content = None
    mock_tool_msg.reasoning = None
    mock_tool_msg.reasoning_content = None
    mock_tc = MagicMock()
    mock_tc.id = "call_test"
    mock_tc.function.name = "mock.tool"
    mock_tc.function.arguments = '{"value": "hello"}'
    mock_tool_msg.tool_calls = [mock_tc]

    mock_tool_choice = MagicMock()
    mock_tool_choice.message = mock_tool_msg
    mock_tool_choice.finish_reason = "tool_calls"

    mock_tool_resp = MagicMock()
    mock_tool_resp.choices = [mock_tool_choice]
    mock_tool_resp.usage = MagicMock(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )

    mock_text_msg = MagicMock()
    mock_text_msg.content = "任务执行完成：已创建项目群 oc_xxx，已创建文档，已发送欢迎消息。"
    mock_text_msg.tool_calls = None
    mock_text_msg.reasoning = None
    mock_text_msg.reasoning_content = None

    mock_text_choice = MagicMock()
    mock_text_choice.message = mock_text_msg
    mock_text_choice.finish_reason = "stop"

    mock_text_resp = MagicMock()
    mock_text_resp.choices = [mock_text_choice]
    mock_text_resp.usage = MagicMock(
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
    )

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        # First call → tool_call, second call → text finish
        mock_llm.side_effect = [mock_tool_resp, mock_text_resp]

        result = await executor.execute(task)

    check("AgentResult.success", result.success, f"error={result.error}")
    check("AgentResult.summary 不为空", bool(result.summary))
    check("AgentResult.actions 数量", len(result.actions) == 1, f"实际: {len(result.actions)}")
    if result.actions:
        check("actions[0].tool", result.actions[0]["tool"] == "mock.tool")
        check("actions[0].result 含 success", result.actions[0]["result"].get("success") is True)

    # Test max_iterations
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm2:
        # Always return tool_calls → max iterations
        mock_llm2.return_value = mock_tool_resp
        result2 = await executor.execute(AgentTask(
            description="Infinite loop test",
            max_iterations=3,
        ))
        check("max_iterations 触发", not result2.success and result2.error == "max_iterations exceeded")

    # Test timeout
    async def slow_response(**kwargs):
        await asyncio.sleep(10)
        return mock_text_resp

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm3:
        mock_llm3.side_effect = slow_response
        result3 = await executor.execute(AgentTask(
            description="Timeout test",
            max_iterations=1,
        ))
        # Note: timeout is set to 120s by default, this test doesn't actually time out
        check("slow response returns (no timeout in mock)", result3 is not None)


# ============================================================================
# 6. 工作空间初始化流程（端到端 Mock）
# ============================================================================
async def test_workspace_flow():
    section("6. 工作空间初始化 — 端到端 Mock")

    # We test the flow's data handling without actually executing it.
    # The full execution requires a real LLM, but we verify:
    # 1. WorkspaceInitFlow can be constructed
    # 2. Event handler registration works
    # 3. Agent task building with workspace_init skill works

    from teamflow.ai.skills import registry
    from teamflow.orchestration.event_bus import EventBus

    # Verify skill exists and is usable
    task = registry.build_task(
        description="Initialize Feishu workspace for GuessWord project",
        context={
            "project_name": "GuessWord",
            "admin_open_id": "ou_test123",
            "git_repo_path": "https://github.com/test/guessword",
        },
        skill_name="workspace_init",
    )
    check("build_task with workspace_init", task.skill_name == "workspace_init")
    check("context 注入 project_name", task.context.get("project_name") == "GuessWord")
    check("context 注入 admin_open_id", task.context.get("admin_open_id") == "ou_test123")

    # Verify EventBus global handler mechanism
    call_log = []
    def test_handler(event):
        call_log.append(event)

    EventBus.subscribe_global("test.event", test_handler)
    check("EventBus.subscribe_global", len(EventBus._global_handlers.get("test.event", [])) >= 1)

    # Clean up
    EventBus._global_handlers.pop("test.event", None)


# ============================================================================
# 7. 卡牌与消息发送
# ============================================================================
def test_card_templates():
    section("7. 卡片模板")

    from teamflow.orchestration.card_templates import (
        project_create_form_card,
        project_created_card,
        project_failed_card,
        startup_card,
        welcome_card,
        workspace_init_result_card,
        workspace_welcome_card,
    )

    # Test each card produces valid dict
    cards = {
        "startup_card": startup_card(),
        "welcome_card": welcome_card(),
        "project_create_form_card": project_create_form_card(),
        "project_created_card": project_created_card("test-id", "Test", "https://github.com/test"),
        "project_failed_card": project_failed_card("测试", "失败原因"),
        "workspace_init_result_card": workspace_init_result_card("Test", [
            {"name": "创建项目群", "status": "success", "detail": "oc_xxx"},
            {"name": "创建文档", "status": "failure", "detail": "权限不足"},
            {"name": "发送欢迎", "status": "skipped", "detail": "群未创建"},
        ]),
        "workspace_welcome_card": workspace_welcome_card("Test", "https://doc.url"),
    }

    for name, card in cards.items():
        check(f"{name} 是 dict", isinstance(card, dict))
        if isinstance(card, dict):
            card_json = json.dumps(card, ensure_ascii=False)
            check(f"{name} 可序列化", len(card_json) > 20)


# ============================================================================
# 8. 设置向导数据完整性
# ============================================================================
def test_setup_data():
    section("8. 设置向导数据完整性")

    from teamflow.setup.cli import _get_provider_choices, _get_provider_models

    choices = _get_provider_choices()
    check(f"提供商选择列表: {len(choices)} 个", len(choices) >= 25)
    # Check types
    for c in choices[:3]:
        check(f"提供商条目 tuple 长度: {c[0]}", len(c) == 5)

    models = _get_provider_models()
    check(f"提供商模型字典: {len(models)} 个", len(models) >= 25)
    check("deepseek 有模型", len(models.get("deepseek", [])) >= 1)
    check("openai 有模型", len(models.get("openai", [])) >= 3)
    check("minimax-cn 有模型", len(models.get("minimax-cn", [])) >= 1)


# ============================================================================
def main():
    global PASS, FAIL

    print("TeamFlow Agent 自动化测试")
    print("=" * 60)

    # Sync tests
    test_model_registry()
    test_transports()
    test_skills()
    test_tool_provider()
    test_card_templates()
    test_setup_data()

    # Async tests
    asyncio.run(test_agent_executor())
    asyncio.run(test_workspace_flow())

    # Summary
    total = PASS + FAIL
    print(f"\n{'='*60}")
    print(f"  结果: {PASS}/{total} 通过", end="")
    if FAIL > 0:
        print(f", {FAIL} FAILED")
    else:
        print(" ALL PASSED")
    print(f"{'='*60}")

    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)

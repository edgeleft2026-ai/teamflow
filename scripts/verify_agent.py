#!/usr/bin/env python3
"""End-to-end verification of Agent infrastructure.

Approach:
  Test 1: Config loading & defaults
  Test 2: AgentTask / AgentResult dataclasses
  Test 3: AgentExecutor tool-use loop with ToolProvider + real LLM
  Test 4: Import chain (all modules import cleanly)
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from teamflow.ai.models import MODEL_ROUTING, AgentResult, AgentTask
from teamflow.config.settings import AgentConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("verify")

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        logger.info("  PASS: %s", name)
    else:
        FAIL += 1
        logger.error("  FAIL: %s — %s", name, detail)


# ── Test 1: Config ───────────────────────────────────────────────────────────

def test_config():
    logger.info("=== Test 1: Configuration ===")
    cfg = AgentConfig()
    check("mcp_tools default", cfg.mcp_tools == "im.v1.*,docx.v1.*")
    check("max_iterations default", cfg.max_iterations == 10)
    check("timeout_seconds default", cfg.timeout_seconds == 120)
    check("fast_model default", cfg.fast_model == "openai/gpt-4o-mini")
    check("model_routing has 3 tiers", len(MODEL_ROUTING) == 3)
    logger.info("")


# ── Test 2: Dataclasses ──────────────────────────────────────────────────────

def test_dataclasses():
    logger.info("=== Test 2: Dataclasses ===")

    task = AgentTask(
        description="Test task",
        context={"project_id": "p1", "admin_open_id": "ou_1"},
        complexity="fast",
        max_iterations=5,
        allowed_tools=["add", "echo"],
    )
    check("AgentTask.description", task.description == "Test task")
    check("AgentTask.complexity", task.complexity == "fast")
    check("AgentTask.max_iterations", task.max_iterations == 5)
    check("AgentTask.defaults",
          AgentTask(description="x").complexity == "smart"
          and AgentTask(description="x").max_iterations == 10
          and AgentTask(description="x").context == {}
          and AgentTask(description="x").allowed_tools is None)

    result = AgentResult(
        success=True,
        summary="Done.",
        actions=[{"tool": "add", "args": {"a": 1, "b": 2}}],
        data={"sum": 3},
    )
    check("AgentResult.success", result.success is True)
    check("AgentResult.actions count", len(result.actions) == 1)
    check("AgentResult.defaults",
          AgentResult(success=False, summary="").actions == []
          and AgentResult(success=False, summary="").data is None
          and AgentResult(success=False, summary="").error is None)

    logger.info("")


# ── Test 3: AgentExecutor + ToolProvider + Real LLM ──────────────────────────

async def test_agent_executor():
    logger.info("=== Test 3: AgentExecutor tool-use loop (real LLM) ===")

    from teamflow.ai.agent import AgentExecutor
    from teamflow.ai.tools import ToolDef, ToolProvider

    # Build an in-process tool provider (same interface AgentExecutor expects)
    tools = ToolProvider()

    async def _add(a: int, b: int) -> dict:
        return {"sum": a + b}

    async def _multiply(x: int, y: int) -> dict:
        return {"product": x * y}

    tools.register(ToolDef(
        name="add",
        description="Add two integers. Args: a (int), b (int). Returns: sum.",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
        handler=_add,
    ))
    tools.register(ToolDef(
        name="multiply",
        description="Multiply two integers. Args: x (int), y (int). Returns: product.",
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            "required": ["x", "y"],
        },
        handler=_multiply,
    ))

    executor = AgentExecutor(
        tools,
        model_overrides={"smart": "deepseek/deepseek-chat"},
    )

    task = AgentTask(
        description=(
            "Calculate (3 + 5) * 7 using the available tools. "
            "You will need to call add first, then multiply. "
            "Tell me the final answer."
        ),
        complexity="smart",
        max_iterations=5,
    )

    logger.info("Task: %s", task.description)
    result: AgentResult = await executor.execute(task)

    logger.info("success = %s", result.success)
    logger.info("summary = %s", result.summary[:400] if result.summary else "(empty)")
    logger.info("actions = %d tool calls", len(result.actions))
    for i, a in enumerate(result.actions):
        logger.info("  [%d] %s(%s)", i + 1, a["tool"], json.dumps(a["args"], ensure_ascii=False))

    check("agent completed successfully", result.success, result.error or "")
    check("agent made tool calls", len(result.actions) >= 1,
          f"expected >= 1, got {len(result.actions)}")

    if result.error:
        logger.error("  Error: %s", result.error)

    logger.info("")


# ── Test 4: Import chain & prompts ───────────────────────────────────────────

def test_imports_and_prompts():
    logger.info("=== Test 4: Imports and prompts ===")
    from teamflow.ai import (
        MODEL_ROUTING,
        AgentExecutor,
        AgentResult,
        AgentTask,
        ToolProvider,
    )
    from teamflow.ai.prompts import WORKSPACE_INIT_PROMPT, get_system_prompt

    check("AgentExecutor import", AgentExecutor is not None)
    check("AgentResult import", AgentResult is not None)
    check("AgentTask import", AgentTask is not None)
    check("ToolProvider import", ToolProvider is not None)
    check("WORKSPACE_INIT_PROMPT non-empty", len(WORKSPACE_INIT_PROMPT) > 100)
    check("get_system_prompt('workspace_init')",
          len(get_system_prompt("workspace_init")) > 100)
    check("get_system_prompt('unknown') returns ''",
          get_system_prompt("nonexistent") == "")
    check("MODEL_ROUTING import", len(MODEL_ROUTING) == 3)

    from teamflow.config import FeishuConfig, TeamFlowConfig
    cfg = TeamFlowConfig(feishu=FeishuConfig(app_id="test", app_secret="test"))
    check("TeamFlowConfig with defaults",
          cfg.agent.mcp_tools == "im.v1.*,docx.v1.*"
          and cfg.feishu.app_id == "test")

    logger.info("")


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    global PASS, FAIL

    logger.info("TeamFlow Agent Infrastructure Verification")
    logger.info("==========================================\n")

    test_config()
    test_dataclasses()
    test_imports_and_prompts()
    await test_agent_executor()

    logger.info("==========================================")
    logger.info("Results: %d passed, %d failed, %d total", PASS, FAIL, PASS + FAIL)

    if FAIL > 0:
        logger.error("SOME TESTS FAILED")
        sys.exit(1)
    else:
        logger.info("ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

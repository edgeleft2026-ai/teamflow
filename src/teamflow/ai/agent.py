"""Agent Executor: LiteLLM tool-use loop for multi-step orchestration."""

import asyncio
import json
import logging
import os

import litellm

from teamflow.ai.models import MODEL_ROUTING, AgentResult, AgentTask
from teamflow.ai.skills import registry

logger = logging.getLogger(__name__)

_MCP_TOOL_TYPE = "function"


def _mcp_tools_to_litellm(tools: list) -> list[dict]:
    """Convert MCP Tool objects to LiteLLM/OpenAI function-calling format."""
    result = []
    for tool in tools:
        schema = getattr(tool, "inputSchema", {})
        result.append(
            {
                "type": _MCP_TOOL_TYPE,
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "parameters": schema,
                },
            }
        )
    return result


def _resolve_model(complexity: str, config_override: dict | None = None) -> str:
    """Resolve the LiteLLM model identifier for a given complexity tier.

    Checks env vars TEAMFLOW_FAST_MODEL / TEAMFLOW_SMART_MODEL / TEAMFLOW_REASONING_MODEL
    first, then falls back to MODEL_ROUTING defaults.
    """
    env_key = f"TEAMFLOW_{complexity.upper()}_MODEL"
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    if config_override and complexity in config_override:
        return config_override[complexity]
    return MODEL_ROUTING.get(complexity, MODEL_ROUTING["smart"])


class AgentExecutor:
    """Executes AgentTasks using a LiteLLM tool-use loop with MCP tools."""

    def __init__(self, mcp_client, model_overrides: dict | None = None) -> None:
        """Args:
        mcp_client: MCPClient instance (must be connected).
        model_overrides: Optional dict mapping complexity tier → model name.
        """
        self._mcp = mcp_client
        self._model_overrides = model_overrides or {}

    async def execute(self, task: AgentTask) -> AgentResult:
        """Run the agent tool-use loop for the given task.

        Args:
            task: AgentTask with description, context, complexity, and constraints.

        Returns:
            AgentResult with success status, summary, action list, and optional data.
        """
        tools = _mcp_tools_to_litellm(self._mcp.tools)
        if task.allowed_tools:
            tools = [t for t in tools if t["function"]["name"] in task.allowed_tools]

        model = _resolve_model(task.complexity, self._model_overrides)
        system_prompt = _build_system_prompt(task)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _format_user_message(task)},
        ]

        actions: list[dict] = []
        iteration = 0

        logger.info(
            "Agent start: model=%s max_iterations=%d tools=%d",
            model,
            task.max_iterations,
            len(tools),
        )

        try:
            while iteration < task.max_iterations:
                iteration += 1
                logger.info("Agent iteration %d/%d", iteration, task.max_iterations)

                response = await asyncio.wait_for(
                    litellm.acompletion(
                        model=model,
                        messages=messages,
                        tools=tools if tools else None,
                    ),
                    timeout=120,
                )

                choice = response.choices[0]
                message = choice.message

                if message.tool_calls:
                    # Step A: collect tool-call info & execute MCP calls
                    tool_results: list[dict] = []
                    tc_list: list[dict] = []
                    for tool_call in message.tool_calls:
                        tc_id = tool_call.id
                        if hasattr(tool_call.function, "name"):
                            tc_name = tool_call.function.name
                        else:
                            tc_name = tool_call.function.get("name", "")
                        tc_args_raw = (
                            tool_call.function.arguments
                            if hasattr(tool_call.function, "arguments")
                            else tool_call.function.get("arguments", "{}")
                        )
                        if isinstance(tc_args_raw, str):
                            try:
                                parsed_args = json.loads(tc_args_raw)
                            except json.JSONDecodeError:
                                parsed_args = {"raw": tc_args_raw}
                        else:
                            parsed_args = tc_args_raw

                        tc_list.append(
                            {
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tc_name,
                                    "arguments": tc_args_raw if isinstance(tc_args_raw, str)
                                    else json.dumps(tc_args_raw),
                                },
                            }
                        )

                        logger.info(
                            "Agent tool_call: %s args=%s", tc_name, parsed_args
                        )
                        mcp_result = await self._mcp.call_tool(tc_name, parsed_args)
                        actions.append(
                            {"tool": tc_name, "args": parsed_args, "result": mcp_result}
                        )
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps(mcp_result, ensure_ascii=False),
                            }
                        )

                    # Step B: append assistant message BEFORE tool results (API requirement)
                    assistant_msg: dict = {"role": "assistant", "content": message.content or ""}
                    assistant_msg["tool_calls"] = tc_list
                    messages.append(assistant_msg)

                    # Step C: append tool-result messages
                    messages.extend(tool_results)
                else:
                    content = message.content or ""
                    logger.info("Agent finished after %d iterations", iteration)
                    return AgentResult(
                        success=True,
                        summary=content,
                        actions=actions,
                    )

            # Max iterations reached
            logger.warning("Agent hit max_iterations (%d)", task.max_iterations)
            return AgentResult(
                success=False,
                summary="Agent reached maximum iterations without completing the task.",
                actions=actions,
                error="max_iterations exceeded",
            )

        except TimeoutError:
            logger.error("Agent task timed out")
            return AgentResult(
                success=False,
                summary="Agent task timed out.",
                actions=actions,
                error="timeout",
            )
        except Exception as e:
            logger.exception("Agent task failed with exception")
            return AgentResult(
                success=False,
                summary=f"Agent task failed: {e}",
                actions=actions,
                error=str(e),
            )


def _build_system_prompt(task: AgentTask) -> str:
    """Build the system prompt, using a matched skill when available.

    Resolution order:
    1. If task.skill_name is set, use that skill's prompt (formatted with context).
    2. Otherwise try to match the description against the skill registry.
    3. Fall back to the generic TeamFlow system prompt.
    """
    skill = None
    if task.skill_name:
        skill = registry.get(task.skill_name)
    else:
        skill = registry.match(task.description)

    if skill and skill.system_prompt:
        ctx = task.context or {}
        try:
            skill_prompt = skill.system_prompt.format(**ctx)
        except KeyError as e:
            logger.warning(
                "Skill %s: missing context var %s, using raw prompt",
                skill.name, e
            )
            skill_prompt = skill.system_prompt
        return skill_prompt

    # Generic fallback prompt
    base = (
        "You are TeamFlow, an AI project collaboration assistant running in Feishu (Lark). "
        "Your role is to help users manage projects by interacting with Feishu APIs. "
        "You have access to Feishu tools via MCP (Model Context Protocol).\n\n"
        "Guidelines:\n"
        "- Execute tasks step by step. After each tool call, check the result before proceeding.\n"
        "- If a step fails, report the failure but continue with remaining steps where possible.\n"
        "- Report what you did and what the results were in a clear, concise summary.\n"
        "- Use Chinese (Simplified) for all user-facing output.\n"
        "- Do not delete data, remove members, or perform destructive actions.\n"
        "- If you cannot complete a task, explain why and suggest next steps.\n"
    )

    if task.context:
        ctx_str = json.dumps(task.context, ensure_ascii=False, indent=2)
        base += f"\nContext:\n{ctx_str}\n"

    return base


def _format_user_message(task: AgentTask) -> str:
    """Format the user message with task description and context."""
    parts = [task.description]
    if task.context:
        ctx_str = json.dumps(task.context, ensure_ascii=False, indent=2)
        parts.append(f"\nContext:\n{ctx_str}")
    return "\n".join(parts)

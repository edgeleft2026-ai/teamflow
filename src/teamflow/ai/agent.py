"""Agent Executor: tool-use loop with provider-aware transport layer.

Integrates:
- Transport layer for response normalization and provider detection
- model_registry for capability validation at initialization
- ToolProvider for tool execution
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random

import litellm

from teamflow.ai.model_registry import (
    detect_api_mode,
    get_model_capabilities,
    supports_reasoning,
)
from teamflow.ai.models import MODEL_ROUTING, AgentResult, AgentTask
from teamflow.ai.skills import registry
from teamflow.ai.transports import get_transport

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


def _parse_provider_n_model(model_str: str) -> tuple[str, str]:
    """Parse 'provider/model' or 'model' into (provider, model_name)."""
    if "/" in model_str:
        parts = model_str.split("/", 1)
        return parts[0], parts[1]
    return "", model_str


class AgentExecutor:
    """Executes AgentTasks using a LiteLLM tool-use loop with transport normalization.

    Uses the transport layer for response normalization while keeping LiteLLM
    as the underlying API caller (handles provider routing automatically).
    """

    def __init__(
        self,
        mcp_client,
        model_overrides: dict | None = None,
        provider: str = "",
        timeout_seconds: int = 120,
    ) -> None:
        """Args:
        mcp_client: ToolProvider instance (supports .tools and .call_tool()).
        model_overrides: Optional dict mapping complexity tier → model name.
        provider: Default provider ID (e.g. "openai", "deepseek"). Auto-detected if empty.
        timeout_seconds: LittellM completion timeout.
        """
        self._mcp = mcp_client
        self._model_overrides = model_overrides or {}
        self._provider = provider
        self._timeout = timeout_seconds

    def validate_model(self, complexity: str = "smart") -> bool:
        """Check that the configured model supports tool calling.

        Returns True if the model is known and supports tools, or if unknown
        (we assume it works). Returns False only if the model is known to
        lack tool-calling support.
        """
        model = _resolve_model(complexity, self._model_overrides)
        provider_name, model_name = _parse_provider_n_model(model)
        if not provider_name and self._provider:
            provider_name = self._provider

        if not provider_name:
            return True  # can't validate without provider info

        caps = get_model_capabilities(provider_name, model_name)
        if not caps.get("supports_tools", True):
            logger.error(
                "模型 %s/%s 不支持工具调用，Agent 执行可能会失败",
                provider_name,
                model_name,
            )
            return False
        return True

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
        provider_name, model_name = _parse_provider_n_model(model)
        if not provider_name and self._provider:
            provider_name = self._provider

        api_mode = detect_api_mode(provider_name, model_name)
        transport = get_transport(api_mode)
        model_supports_reasoning = supports_reasoning(provider_name, model_name)

        system_prompt = _build_system_prompt(task)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _format_user_message(task)},
        ]

        actions: list[dict] = []
        iteration = 0
        reasoning_log: list[str] = []

        logger.info(
            "Agent 启动: model=%s api_mode=%s provider=%s max_iterations=%d tools=%d",
            model,
            api_mode,
            provider_name,
            task.max_iterations,
            len(tools),
        )

        try:
            while iteration < task.max_iterations:
                iteration += 1
                logger.info("Agent 迭代 %d/%d", iteration, task.max_iterations)

                # Build LiteLLM kwargs
                litellm_kwargs: dict = {
                    "model": model,
                    "messages": messages,
                }
                if tools:
                    litellm_kwargs["tools"] = tools

                # Override api_base for providers with non-default endpoints
                from teamflow.ai.model_registry import get_litellm_base_url_override
                base_url_override = get_litellm_base_url_override(provider_name)
                if base_url_override:
                    litellm_kwargs["api_base"] = base_url_override

                # Add reasoning config for models that support it
                if model_supports_reasoning:
                    litellm_kwargs["extra_body"] = {
                        "reasoning": {"enabled": True, "effort": "medium"}
                    }

                response = await asyncio.wait_for(
                    _call_with_retry(litellm.acompletion, **litellm_kwargs),
                    timeout=self._timeout,
                )

                # Normalize response through transport layer
                normalized = transport.normalize_response(response)

                # Collect reasoning content
                if normalized.reasoning_content:
                    reasoning_log.append(normalized.reasoning_content)
                if normalized.reasoning:
                    reasoning_log.append(normalized.reasoning)

                if normalized.tool_calls:
                    # Execute tool calls
                    tool_results: list[dict] = []
                    tc_list: list[dict] = []
                    for tc in normalized.tool_calls:
                        tc_id = tc.id
                        tc_name = tc.name
                        tc_args = tc.arguments

                        parsed_args = _safe_parse_json(tc_args)

                        tc_list.append(
                            {
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tc_name,
                                    "arguments": tc_args,
                                },
                            }
                        )

                        logger.info("Agent 工具调用: %s args=%s", tc_name, parsed_args)
                        tool_result = await self._mcp.call_tool(tc_name, parsed_args)
                        actions.append(
                            {
                                "tool": tc_name,
                                "args": parsed_args,
                                "result": tool_result,
                            }
                        )
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps(tool_result, ensure_ascii=False),
                            }
                        )

                    # Append assistant message before tool results (API requirement)
                    assistant_msg: dict = {"role": "assistant", "content": normalized.content or ""}
                    assistant_msg["tool_calls"] = tc_list
                    messages.append(assistant_msg)
                    messages.extend(tool_results)
                else:
                    content = normalized.content or ""
                    logger.info("Agent 在 %d 次迭代后完成", iteration)

                    # Include reasoning log in the result data
                    result_data: dict = {}
                    if reasoning_log:
                        result_data["reasoning"] = reasoning_log

                    return AgentResult(
                        success=True,
                        summary=content,
                        actions=actions,
                        data=result_data or None,
                    )

            # Max iterations reached
            logger.warning("Agent 达到最大迭代次数 (%d)", task.max_iterations)
            return AgentResult(
                success=False,
                summary="Agent reached maximum iterations without completing the task.",
                actions=actions,
                error="max_iterations exceeded",
            )

        except TimeoutError:
            logger.error("Agent 任务超时")
            return AgentResult(
                success=False,
                summary="Agent task timed out.",
                actions=actions,
                error="timeout",
            )
        except Exception as e:
            logger.exception("Agent 任务执行异常")
            return AgentResult(
                success=False,
                summary=f"Agent task failed: {e}",
                actions=actions,
                error=str(e),
            )


def _safe_parse_json(raw: str) -> dict:
    """Safely parse a JSON string, returning a fallback dict on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


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
                "技能 %s: 缺少上下文变量 %s，使用原始提示词",
                skill.name, e,
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


async def _call_with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs,
):
    """Call an async function with exponential backoff retry on transient errors."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt >= max_retries:
                break
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "LiteLLM 调用失败 (attempt %d/%d): %s, %.1fs 后重试",
                attempt + 1, max_retries + 1, e, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc

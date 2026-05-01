"""Agent tool system: register Python async functions as Agent tools.

ToolProvider replaces the MCP subprocess approach with direct Python calls.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    """Definition of a callable tool for the Agent.

    Args:
        name: Unique tool name, e.g. "im.v1.chat.create".
        description: Natural language description shown to the LLM.
        parameters: JSON Schema for the tool's input.
        handler: Async callable that receives keyword arguments matching
                 the schema properties and returns a dict.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any] | None = None


class ToolProvider:
    """Registry of ToolDef instances that the Agent Executor can use.

    Provides the same interface as the old MCPClient (``.tools``, ``.call_tool()``)
    so the AgentExecutor works without changes.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._connected = True

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list:
        """Return tools in the shape the AgentExecutor expects.

        Each entry has ``.name``, ``.description``, ``.inputSchema``.
        """
        result = []
        for t in self._tools.values():
            result.append(
                type(
                    "ToolProxy",
                    (),
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.parameters,
                    },
                )()
            )
        return result

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a registered tool by name."""
        tool = self._tools.get(name)
        if tool is None:
            return {"success": False, "result": None, "error": f"Unknown tool: {name}"}
        if tool.handler is None:
            return {"success": False, "result": None, "error": f"Tool {name} has no handler"}

        logger.info("工具调用: %s args=%s", name, arguments)
        try:
            result = await tool.handler(**arguments)
            logger.info("工具 %s 调用成功", name)
            return {
                "success": True,
                "result": [json.dumps(result, ensure_ascii=False)],
                "error": None,
            }
        except Exception as e:
            logger.error("工具 %s 调用失败: %s", name, e)
            return {"success": False, "result": None, "error": str(e)}

    async def disconnect(self) -> None:
        self._connected = False

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)


# Global singleton.
tool_provider = ToolProvider()


# ── Register built-in Feishu tools ───────────────────────────────────────

from teamflow.ai.tools.feishu import ALL_TOOLS  # noqa: E402

for _tdef in ALL_TOOLS:
    tool_provider.register(
        ToolDef(
            name=_tdef["name"],
            description=_tdef["description"],
            parameters=_tdef["parameters"],
            handler=_tdef["handler"],
        )
    )

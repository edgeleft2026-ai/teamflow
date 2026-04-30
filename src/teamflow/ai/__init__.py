"""AI layer: tool provider, agent executor, model routing, skill system, prompt management."""

from teamflow.ai.agent import AgentExecutor
from teamflow.ai.models import MODEL_ROUTING, AgentResult, AgentTask
from teamflow.ai.prompts import WORKSPACE_INIT_PROMPT, get_system_prompt
from teamflow.ai.skills import Skill, SkillRegistry, registry
from teamflow.ai.tools import ToolDef, ToolProvider, tool_provider

__all__ = [
    "AgentExecutor",
    "AgentResult",
    "AgentTask",
    "MODEL_ROUTING",
    "Skill",
    "SkillRegistry",
    "ToolDef",
    "ToolProvider",
    "WORKSPACE_INIT_PROMPT",
    "get_system_prompt",
    "registry",
    "tool_provider",
]

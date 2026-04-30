"""AI layer: tool provider, agent executor, model routing, skill system, transport layer."""

from teamflow.ai.agent import AgentExecutor
from teamflow.ai.model_registry import (
    CANONICAL_PROVIDERS,
    get_model_capabilities,
    get_model_info,
    get_provider_entry,
    list_models,
    list_providers,
)
from teamflow.ai.models import MODEL_ROUTING, AgentResult, AgentTask
from teamflow.ai.prompts import WORKSPACE_INIT_PROMPT, get_system_prompt
from teamflow.ai.skills import Skill, SkillRegistry, registry
from teamflow.ai.tools import ToolDef, ToolProvider, tool_provider
from teamflow.ai.transports import (
    NormalizedResponse,
    ToolCall,
    Usage,
    get_transport,
)

__all__ = [
    "AgentExecutor",
    "AgentResult",
    "AgentTask",
    "MODEL_ROUTING",
    "NormalizedResponse",
    "Skill",
    "SkillRegistry",
    "ToolCall",
    "ToolDef",
    "ToolProvider",
    "Usage",
    "WORKSPACE_INIT_PROMPT",
    "get_model_capabilities",
    "get_model_info",
    "CANONICAL_PROVIDERS",
    "get_provider_entry",
    "get_system_prompt",
    "get_transport",
    "list_models",
    "list_providers",
    "registry",
    "tool_provider",
]

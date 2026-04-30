"""Agent task and result data structures, plus model routing configuration."""

from dataclasses import dataclass, field


@dataclass
class AgentTask:
    """Input to the Agent Executor.

    Args:
        description: Natural language task description.
        context: Structured context dict (project_id, user info, etc.).
        complexity: Model tier to use — "fast", "smart", or "reasoning".
        max_iterations: Maximum tool-use loop iterations to prevent runaway loops.
        allowed_tools: Optional whitelist of MCP tool names. None means all available.
        skill_name: Optional skill name — when set, the AgentExecutor will use
                    the skill's system prompt and merge constraints.
    """

    description: str
    context: dict = field(default_factory=dict)
    complexity: str = "smart"
    max_iterations: int = 10
    allowed_tools: list[str] | None = None
    skill_name: str | None = None


@dataclass
class AgentResult:
    """Output from the Agent Executor.

    Args:
        success: Whether the agent completed the task successfully.
        summary: Human-readable summary of what the agent did.
        actions: List of tool calls made (for audit trail).
        data: Structured output data (chat_id, doc_url, etc.).
        error: Error message if success is False.
    """

    success: bool
    summary: str
    actions: list[dict] = field(default_factory=list)
    data: dict | None = None
    error: str | None = None


# Model routing: complexity tier → LiteLLM model identifier.
# Fast models are cheap/low-latency; reasoning models for complex analysis.
MODEL_ROUTING: dict[str, str] = {
    "fast": "openai/gpt-4o-mini",
    "smart": "openai/gpt-4o",
    "reasoning": "openai/gpt-4o",
}

# LiteLLM model identifiers for optional environment variable override.
# Set TEAMFLOW_FAST_MODEL, TEAMFLOW_SMART_MODEL, TEAMFLOW_REASONING_MODEL
# to override the defaults.

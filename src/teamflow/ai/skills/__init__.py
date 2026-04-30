"""Agent skill system: register, match, and enrich AgentTasks with skill configuration.

A Skill bundles a system prompt, tool whitelist, and model routing together
under a name and trigger set. The SkillRegistry matches incoming tasks to skills
and injects the skill's configuration into the AgentTask.

Skills are registered at import time — import the registry and call
``registry.register(skill)`` during module initialization.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from teamflow.ai.models import AgentTask

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A named agent capability that bundles prompt, tools, and routing.

    Args:
        name: Unique identifier, e.g. "workspace_init".
        description: Human-readable description shown in skill listings.
        triggers: List of keywords or regex patterns. When the task description
                  matches any trigger, this skill is activated.
        system_prompt: The system prompt template. May contain Python
                       ``{placeholder}`` variables filled from task.context.
        allowed_tools: Optional whitelist of MCP tool names. None means all.
        complexity: Override for the AgentTask complexity tier.
        max_iterations: Override for max tool-use loop iterations.
    """

    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    system_prompt: str = ""
    allowed_tools: list[str] | None = None
    complexity: str | None = None
    max_iterations: int | None = None

    def matches(self, description: str) -> bool:
        """Check whether this skill should handle the given task description.

        Each trigger is tested against the lowercased description:
        - If the trigger starts and ends with ``/``, it is treated as a regex.
        - Otherwise it is matched as a case-insensitive substring.
        """
        lower = description.lower()
        for trigger in self.triggers:
            if trigger.startswith("/") and trigger.endswith("/"):
                try:
                    if re.search(trigger[1:-1], lower):
                        return True
                except re.error:
                    logger.warning(
                        "Skill %s has invalid regex trigger: %s", self.name, trigger
                    )
                    continue
            elif trigger.lower() in lower:
                return True
        return False

    def apply(self, task: AgentTask) -> AgentTask:
        """Return a new AgentTask enriched with this skill's configuration.

        Skill values take precedence over the original task fields. The
        skill's system_prompt is NOT formatted here — that happens at execution
        time when the full task.context is available.
        """
        return AgentTask(
            description=task.description,
            context=task.context or {},
            complexity=self.complexity or task.complexity,
            max_iterations=self.max_iterations or task.max_iterations,
            allowed_tools=(
                self.allowed_tools
                if self.allowed_tools is not None
                else task.allowed_tools
            ),
            skill_name=self.name,
        )


class SkillRegistry:
    """Thread-safe registry of all available Agent skills.

    Skills are registered at import time (by loading skill modules) and
    matched against task descriptions at runtime.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill. Replaces any existing skill with the same name."""
        if skill.name in self._skills:
            logger.warning("Skill %s is being replaced", skill.name)
        self._skills[skill.name] = skill
        logger.info(
            "Registered skill: %s (triggers=%s)", skill.name, skill.triggers
        )

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    def match(self, description: str) -> Skill | None:
        """Find the first skill whose triggers match the description.

        Skills are checked in registration order. Returns None if no match.
        """
        for skill in self._skills.values():
            if skill.matches(description):
                logger.info("Skill matched: %s", skill.name)
                return skill
        return None

    def list(self) -> list[Skill]:
        """Return all registered skills."""
        return list(self._skills.values())

    def build_task(
        self,
        description: str,
        context: dict | None = None,
        *,
        skill_name: str | None = None,
        **kwargs,
    ) -> AgentTask:
        """Convenience: build an AgentTask, optionally matching a skill.

        If ``skill_name`` is given, look it up directly. Otherwise attempt to
        match the description against registered skills. When a skill is found
        its configuration is merged into the resulting AgentTask.

        Args:
            description: Natural language task description.
            context: Structured context dict.
            skill_name: Optional explicit skill name (bypasses trigger matching).
            **kwargs: Additional AgentTask fields (complexity, etc.).

        Returns:
            An AgentTask enriched with skill configuration if a skill matched.
        """
        task = AgentTask(description=description, context=context or {}, **kwargs)
        skill = None
        if skill_name:
            skill = self.get(skill_name)
        else:
            skill = self.match(description)
        if skill:
            task = skill.apply(task)
        return task


# Global skill registry singleton.
registry = SkillRegistry()


# Convenience decorator for registering skills.
def register_skill(
    name: str,
    description: str,
    triggers: list[str] | None = None,
    system_prompt: str = "",
    allowed_tools: list[str] | None = None,
    complexity: str | None = None,
    max_iterations: int | None = None,
) -> Callable:
    """Decorator that builds and registers a Skill from a function that returns
    its system prompt (or None).

    Usage::

        @register_skill(
            name="my_skill",
            description="Does something useful",
            triggers=["do something"],
            allowed_tools=["tool.a", "tool.b"],
        )
        def my_skill_prompt() -> str:
            return "You are a helpful assistant..."
    """

    def decorator(fn: Callable) -> Callable:
        prompt = fn() if callable(fn) else ""
        skill = Skill(
            name=name,
            description=description,
            triggers=triggers or [],
            system_prompt=prompt,
            allowed_tools=allowed_tools,
            complexity=complexity,
            max_iterations=max_iterations,
        )
        registry.register(skill)
        return fn

    return decorator


# Load built-in skill modules.
from teamflow.ai.skills.workspace_init import register_workspace_skill  # noqa: E402

register_workspace_skill()

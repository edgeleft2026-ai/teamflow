"""Agent skill system — file-driven, SKILL.md auto-discovery.

Drop a ``SKILL.md`` into ``skills/<name>/`` and it's automatically picked up.
Users can also add skills under ``~/.teamflow/skills/<name>/SKILL.md``.

Frontmatter format (YAML)::

    ---
    name: my-skill
    description: "What this skill does"
    triggers:
      - "keyword"
      - "/regex pattern/"
    allowed_tools:
      - "im.v1.chat.create"
    complexity: smart
    max_iterations: 10
    ---
    # Prompt content (Markdown)
    You are a ...

Each SKILL.md becomes a ``Skill`` registered in the global ``registry``.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from teamflow.ai.models import AgentTask

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A named agent capability that bundles prompt, tools, and routing.

    Args:
        name: Unique identifier, e.g. "workspace_init".
        description: Human-readable description.
        triggers: List of keywords or regex patterns.
        system_prompt: The system prompt (may contain ``{placeholder}`` vars).
        allowed_tools: Optional whitelist of tool names. None means all.
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
                        "技能 %s 的正则触发器无效: %s", self.name, trigger
                    )
                    continue
            elif trigger.lower() in lower:
                return True
        return False

    def apply(self, task: AgentTask) -> AgentTask:
        """Return a new AgentTask enriched with this skill's configuration.

        Skill values take precedence over the original task fields.
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

    Skills are auto-discovered from SKILL.md files at startup.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill. Replaces any existing skill with the same name."""
        if skill.name in self._skills:
            logger.warning("技能 %s 被替换", skill.name)
        self._skills[skill.name] = skill
        logger.info("已注册技能: %s", skill.name)

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    def match(self, description: str) -> Skill | None:
        """Find the first skill whose triggers match the description.

        Skills are checked in registration order. Returns None if no match.
        """
        for skill in self._skills.values():
            if skill.matches(description):
                logger.info("技能匹配: %s", skill.name)
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
        """Build an AgentTask, optionally matching a skill.

        If ``skill_name`` is given, look it up directly. Otherwise attempt to
        match the description against registered skills.
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

    # ── Auto-discovery of SKILL.md files ────────────────────────────────

    def discover_from_dir(self, skills_dir: str | Path) -> int:
        """Scan a directory for ``<skill>/SKILL.md`` files and register them.

        Returns the number of skills registered.
        """
        skills_dir = Path(skills_dir)
        if not skills_dir.is_dir():
            return 0

        count = 0
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue

            try:
                skill = self._load_skill_from_md(skill_md)
                if skill:
                    self.register(skill)
                    count += 1
            except Exception:
                logger.exception("加载技能文件失败: %s", skill_md)

        return count

    def _load_skill_from_md(self, path: Path) -> Skill | None:
        """Parse a SKILL.md file into a Skill object."""
        text = path.read_text(encoding="utf-8")

        # Split frontmatter from body
        meta, body = _parse_frontmatter(text)
        if not meta.get("name"):
            logger.warning("SKILL.md %s 缺少 'name' 前置元数据，跳过", path)
            return None

        # Parse triggers — support both YAML list and inline names
        triggers: list[str] = []
        raw_triggers = meta.get("triggers", [])
        if isinstance(raw_triggers, list):
            triggers = [str(t) for t in raw_triggers]
        elif isinstance(raw_triggers, str):
            triggers = [raw_triggers]

        # Auto-derive triggers from description if none specified
        if not triggers:
            desc = meta.get("description", "")
            triggers = _extract_triggers_from_text(meta["name"], desc)

        # Add the skill name itself as a trigger
        name = meta["name"]
        if name not in triggers:
            triggers.insert(0, name)

        # Parse allowed_tools
        allowed_tools: list[str] | None = None
        raw_tools = meta.get("allowed_tools")
        if isinstance(raw_tools, list):
            allowed_tools = [str(t) for t in raw_tools]
        elif isinstance(raw_tools, str):
            allowed_tools = [raw_tools]

        return Skill(
            name=name,
            description=str(meta.get("description", "")),
            triggers=triggers,
            system_prompt=body,
            allowed_tools=allowed_tools,
            complexity=meta.get("complexity"),
            max_iterations=_parse_optional_int(meta.get("max_iterations")),
        )


# ── Frontmatter parser ──────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns (metadata_dict, body_text).
    If no valid frontmatter is found, returns ({}, text).
    """
    text = text.strip()
    if not text.startswith("---"):
        return {}, text

    idx = text.find("---", 3)
    if idx == -1:
        return {}, text

    fm_text = text[3:idx].strip()
    body = text[idx + 3:].strip()

    meta: dict = {}
    current_key: str | None = None
    current_list: list = []

    for raw_line in fm_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Check for list item: "  - value"
        list_match = re.match(r"^\s*-\s+(.+)$", line)
        if list_match and current_key:
            current_list.append(list_match.group(1).strip().strip('"'))
            continue

        # Key: value or key:
        kv_match = re.match(r'^(\w[\w_-]*)\s*:\s*(.*)$', line)
        if kv_match:
            # Flush previous list
            if current_key and current_list:
                meta[current_key] = current_list
                current_list = []
                current_key = None

            key = kv_match.group(1)
            val = kv_match.group(2).strip().strip('"')
            if val:
                meta[key] = val
                current_key = None
            else:
                current_key = key
                current_list = []

    # Flush final list
    if current_key and current_list:
        meta[current_key] = current_list

    return meta, body


def _extract_triggers_from_text(name: str, text: str) -> list[str]:
    """Extract short trigger keywords from text."""
    triggers: list[str] = []
    # Extract Chinese words (2-6 chars)
    cn_words = re.findall(r"[一-鿿]{2,6}", text)
    triggers.extend(cn_words[:5])
    # Extract English words (3+ chars)
    en_words = re.findall(r"\b[a-zA-Z]{3,12}\b", text)
    _stop_words = {"the", "and", "for", "use", "with", "that", "this", "from"}
    triggers.extend(w for w in en_words[:3] if w.lower() not in _stop_words)
    return triggers


def _parse_optional_int(val: object) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ── Global singleton ────────────────────────────────────────────────────

registry = SkillRegistry()


# Convenience decorator for programmatic registration (backward compat).
def register_skill(
    name: str,
    description: str,
    triggers: list[str] | None = None,
    system_prompt: str = "",
    allowed_tools: list[str] | None = None,
    complexity: str | None = None,
    max_iterations: int | None = None,
) -> Callable:
    """Decorator that builds and registers a Skill from a function."""

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


# ── Built-in skill directories to scan ──────────────────────────────────

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent
_USER_SKILLS_DIR = Path(os.path.expanduser("~/.teamflow/skills"))


def _discover_all_skills() -> None:
    """Scan all skill directories and register discovered skills."""
    # Built-in skills (project)
    builtin_count = registry.discover_from_dir(_BUILTIN_SKILLS_DIR)
    logger.info("从 %s 发现 %d 个内置技能", builtin_count, _BUILTIN_SKILLS_DIR)

    # User skills (~/.teamflow/skills/)
    if _USER_SKILLS_DIR.is_dir():
        user_count = registry.discover_from_dir(_USER_SKILLS_DIR)
        logger.info("从 %s 发现 %d 个用户技能", user_count, _USER_SKILLS_DIR)


# Run discovery at import time.
_discover_all_skills()

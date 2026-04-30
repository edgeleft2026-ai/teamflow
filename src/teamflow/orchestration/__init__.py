"""Orchestration layer: command routing, state machines, event bus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from teamflow.orchestration.event_bus import EventBus

if TYPE_CHECKING:
    from teamflow.orchestration.command_router import CommandRouter
    from teamflow.orchestration.project_flow import ProjectCreateFlow

__all__ = [
    "CommandRouter",
    "EventBus",
    "ProjectCreateFlow",
]


def __getattr__(name: str) -> Any:
    """按需导出重量级模块，避免包初始化时产生循环依赖。"""
    if name == "CommandRouter":
        from teamflow.orchestration.command_router import CommandRouter

        return CommandRouter
    if name == "ProjectCreateFlow":
        from teamflow.orchestration.project_flow import ProjectCreateFlow

        return ProjectCreateFlow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

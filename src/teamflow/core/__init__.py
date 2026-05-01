"""Core domain: enums, shared types, logging, and result types."""

from teamflow.core.enums import (
    ActionResult,
    EventStatus,
    FlowState,
    FormStatus,
    ProjectStatus,
    WorkspaceStatus,
)
from teamflow.core.logging import (
    get_correlation_id,
    get_logger,
    redact_dict,
    set_correlation_id,
    setup_logging,
)
from teamflow.core.result import Result
from teamflow.core.types import (
    CardActionData,
    CardActionHandleResult,
    ChatMemberEventData,
    FeishuEvent,
)

__all__ = [
    "ActionResult",
    "CardActionData",
    "CardActionHandleResult",
    "ChatMemberEventData",
    "EventStatus",
    "FeishuEvent",
    "FlowState",
    "FormStatus",
    "ProjectStatus",
    "Result",
    "WorkspaceStatus",
    "get_correlation_id",
    "get_logger",
    "redact_dict",
    "set_correlation_id",
    "setup_logging",
]

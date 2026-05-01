"""Unified Result type for error propagation across all layers.

Replaces ad-hoc (success, error) tuples and except Exception: logger.exception()
swallowing patterns with explicit error propagation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    """Explicit success/failure wrapper for operations that can fail.

    Usage:
        def do_thing() -> Result[int]:
            try:
                value = risky_operation()
                return Result.ok(value)
            except Exception as e:
                return Result.err(str(e))

        result = do_thing()
        if result:
            print(f"success: {result.unwrap()}")
        else:
            print(f"error: {result.error}")
    """

    success: bool
    value: T | None = None
    error: str | None = None
    warning: str | None = None

    @classmethod
    def ok(cls, value: T | None = None, warning: str | None = None) -> Result[T]:
        return cls(success=True, value=value, warning=warning)

    @classmethod
    def err(cls, error: str, warning: str | None = None) -> Result[T]:
        return cls(success=False, error=error, warning=warning)

    def unwrap(self) -> T:
        """Return value if success, raise RuntimeError otherwise."""
        if not self.success:
            raise RuntimeError(f"Called unwrap() on failed result: {self.error}")
        if self.value is None:
            raise RuntimeError("Called unwrap() on success result with None value")
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Return value if success, return default otherwise."""
        if self.success and self.value is not None:
            return self.value
        return default

    def __bool__(self) -> bool:
        return self.success

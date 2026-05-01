"""Tests for core/result.py — unified Result type."""

import pytest

from teamflow.core.result import Result


class TestResultOk:
    def test_ok_creates_success_result(self):
        result = Result.ok(42)
        assert result.success is True
        assert result.value == 42
        assert result.error is None

    def test_ok_with_warning(self):
        result = Result.ok(42, warning="partial failure")
        assert result.success is True
        assert result.value == 42
        assert result.warning == "partial failure"

    def test_ok_with_none_value(self):
        result = Result.ok(None)
        assert result.success is True
        assert result.value is None

    def test_ok_truthey(self):
        result = Result.ok("value")
        assert result
        assert bool(result) is True


class TestResultErr:
    def test_err_creates_failure_result(self):
        result = Result.err("something went wrong")
        assert result.success is False
        assert result.error == "something went wrong"
        assert result.value is None

    def test_err_with_warning(self):
        result = Result.err("failed", warning="retry later")
        assert result.success is False
        assert result.error == "failed"
        assert result.warning == "retry later"

    def test_err_falsy(self):
        result = Result.err("error")
        assert not result
        assert bool(result) is False


class TestResultUnwrap:
    def test_unwrap_returns_value_on_success(self):
        result = Result.ok(42)
        assert result.unwrap() == 42

    def test_unwrap_raises_on_failure(self):
        result = Result.err("bad")
        with pytest.raises(RuntimeError, match="bad"):
            result.unwrap()

    def test_unwrap_raises_on_none_success(self):
        result = Result.ok(None)
        with pytest.raises(RuntimeError, match="None value"):
            result.unwrap()

    def test_unwrap_or_returns_value_on_success(self):
        result = Result.ok(42)
        assert result.unwrap_or(0) == 42

    def test_unwrap_or_returns_default_on_failure(self):
        result = Result.err("bad")
        assert result.unwrap_or(0) == 0

    def test_unwrap_or_returns_default_on_none_value(self):
        result = Result.ok(None)
        assert result.unwrap_or(0) == 0


class TestResultGeneric:
    def test_result_with_string(self):
        result = Result.ok("hello")
        assert result.unwrap() == "hello"

    def test_result_with_list(self):
        result = Result.ok([1, 2, 3])
        assert result.unwrap() == [1, 2, 3]

    def test_result_with_dict(self):
        result = Result.ok({"a": 1})
        assert result.unwrap() == {"a": 1}

"""SQL guardrail tests. TODO(milestone 5): injection/rejection matrix."""

from src.tools.sql import UnsafeQueryError


def test_unsafe_query_error_type():
    assert issubclass(UnsafeQueryError, ValueError)
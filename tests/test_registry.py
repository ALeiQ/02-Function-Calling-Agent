"""Tool registry: registration, schema generation, dispatch and error contract."""

import pydantic
import pytest

from src.tools import DuplicateToolError, ToolError, execute, registry, tool, tool_names

_TEST_NAME = "__test_registry_tool__"


def _make_test_tool(name: str = _TEST_NAME, *, raises: type[Exception] | None = None):
    class Args(pydantic.BaseModel):
        x: str

    def impl(x: str) -> str:
        if raises is not None:
            raise raises(f"boom: {x}")
        return f"processed {x}"

    tool(name=name, description="测试工具", args=Args)(impl)
    return name


def _cleanup(name: str = _TEST_NAME) -> None:
    from src.tools.registry import _TOOLS

    _TOOLS.pop(name, None)


def test_builtin_tools_registered() -> None:
    names = tool_names()
    assert {"calculator", "weather", "sql", "now"} <= set(names)


def test_schema_shape() -> None:
    for definition in registry():
        assert definition["type"] == "function"
        fn = definition["function"]
        assert fn["name"]
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"


def test_register_and_dispatch() -> None:
    name = _make_test_tool()
    try:
        result = execute({"function": {"name": name, "arguments": {"x": "hello"}}})
        assert result == "processed hello"
    finally:
        _cleanup(name)


def test_duplicate_name_rejected() -> None:
    name = _make_test_tool()
    try:
        with pytest.raises(DuplicateToolError):
            _make_test_tool(name)
    finally:
        _cleanup(name)


def test_validation_error_returns_error_message() -> None:
    name = _make_test_tool()
    try:
        result = execute({"function": {"name": name, "arguments": {"x": 123}}})
        assert result.startswith("ERROR: 参数校验失败")
    finally:
        _cleanup(name)


def test_tool_error_returned_not_propagated() -> None:
    name = _make_test_tool(raises=ToolError)
    try:
        result = execute({"function": {"name": name, "arguments": {"x": "a"}}})
        assert result == "ERROR: boom: a"
    finally:
        _cleanup(name)


def test_unknown_tool() -> None:
    result = execute({"function": {"name": "definitely_missing", "arguments": {}}})
    assert result.startswith("ERROR: 未注册的工具")


def test_non_dict_arguments() -> None:
    name = _make_test_tool()
    try:
        result = execute({"function": {"name": name, "arguments": [1, 2]}})
        assert result.startswith("ERROR: 工具参数必须是 JSON 对象")
    finally:
        _cleanup(name)


def test_missing_function_field() -> None:
    result = execute({"not_function": {}})
    assert result.startswith("ERROR:")

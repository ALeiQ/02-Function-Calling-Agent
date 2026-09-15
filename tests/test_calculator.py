"""Calculator: safe AST evaluation and tool dispatch."""

import pytest

from src.tools import execute
from src.tools.calculator import CalculationError, evaluate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2+3", "5"),
        ("(12*8+9)/5", "21"),
        ("10/4", "2.5"),
        ("-3*2", "-6"),
        ("(2+3)*4-1", "19"),
        ("1.5+2.5", "4"),
        (" 7 *  8 ", "56"),
    ],
)
def test_evaluate_valid(expression: str, expected: str) -> None:
    assert evaluate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "   ",
        "1/0",
        "import os",
        "__import__('os')",
        "open('x')",
        "1; 2",
        "2 + x",
        "eval('1')",
    ],
)
def test_evaluate_rejects_unsafe(expression: str) -> None:
    with pytest.raises(CalculationError):
        evaluate(expression)


def test_division_by_zero_message() -> None:
    with pytest.raises(CalculationError, match="除数"):
        evaluate("1/0")


def test_dispatch_success() -> None:
    result = execute(
        {"function": {"name": "calculator", "arguments": {"expression": "3*4"}}}
    )
    assert result == "12"


def test_dispatch_validation_error() -> None:
    result = execute({"function": {"name": "calculator", "arguments": {"expression": "1/0"}}})
    assert result.startswith("ERROR:")


def test_dispatch_missing_args() -> None:
    result = execute({"function": {"name": "calculator"}})
    assert result.startswith("ERROR: 参数校验失败")

"""Calculator tool tests. TODO(milestone 5): value-level cases."""

from src.tools.calculator import CalculationError


def test_calculation_error_type():
    assert issubclass(CalculationError, ValueError)
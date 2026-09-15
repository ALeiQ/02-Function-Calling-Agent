"""Tool registry tests. TODO(milestone 5): full coverage."""

from src.tools import registry


def test_tool_registration_api_surface():
    assert callable(registry.tool)
    assert callable(registry.registry)
    assert callable(registry.execute)
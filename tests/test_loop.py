"""Agent loop tests (mock model client). TODO(milestone 5): full coverage."""

from src.agent import loop


def test_loop_api_surface():
    assert callable(loop.chat)
    assert callable(loop.chat_stream)

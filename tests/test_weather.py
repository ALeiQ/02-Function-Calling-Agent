"""Weather: mock dataset lookup and city-not-found handling."""

import pytest

from src.tools import execute
from src.tools.weather import CityNotFoundError, get_weather


def test_known_city_chinese() -> None:
    result = get_weather("北京")
    assert "北京" in result
    assert "°C" in result


def test_known_city_pinyin_alias() -> None:
    result = get_weather("beijing")
    assert result.startswith("北京当前天气:")


def test_unknown_city_raises() -> None:
    with pytest.raises(CityNotFoundError, match="未收录"):
        get_weather("火星")


def test_dispatch_success() -> None:
    result = execute({"function": {"name": "weather", "arguments": {"city": "上海"}}})
    assert result.startswith("上海当前天气:")


def test_dispatch_unknown_city_error() -> None:
    result = execute({"function": {"name": "weather", "arguments": {"city": "火星"}}})
    assert result.startswith("ERROR:")

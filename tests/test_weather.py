"""Weather: real-time lookup against Open-Meteo (HTTP layer mocked offline)."""

import pytest
import requests

from src.tools import execute
from src.tools import weather as weather_mod
from src.tools.registry import ToolError
from src.tools.weather import CityNotFoundError, get_weather

_CURRENT = {
    "temperature_2m": 22,
    "relative_humidity_2m": 45,
    "weather_code": 0,
    "wind_speed_10m": 12,
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._payload


def patch_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    results: list[dict] | None = None,
    current: dict | None = None,
    error: Exception | None = None,
) -> None:
    def fake_get(url, params=None, timeout=None, **kwargs):
        if error:
            raise error
        if "geocoding" in url:
            return FakeResponse({"results": results or []})
        return FakeResponse({"current": current or _CURRENT})

    monkeypatch.setattr(weather_mod.requests, "get", fake_get)


def test_known_city_realtime(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(
        monkeypatch,
        results=[{"name": "北京", "latitude": 39.9, "longitude": 116.4}],
        current={
            "temperature_2m": 8,
            "relative_humidity_2m": 30,
            "weather_code": 3,
            "wind_speed_10m": 20,
        },
    )
    result = get_weather("北京")
    assert result.startswith("北京当前天气(实时):")
    assert "8" in result
    assert "°C" in result
    assert "20 km/h" in result


def test_pinyin_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(
        monkeypatch,
        results=[{"name": "北京", "latitude": 39.9, "longitude": 116.4}],
    )
    result = get_weather("beijing")
    assert result.startswith("北京当前天气(实时):")


def test_unknown_city_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(monkeypatch, results=[])
    with pytest.raises(CityNotFoundError, match="未找到城市"):
        get_weather("火星")


def test_http_error_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(monkeypatch, error=requests.RequestException("network down"))
    with pytest.raises(ToolError, match="天气服务暂时不可用"):
        get_weather("北京")


def test_dispatch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(
        monkeypatch,
        results=[{"name": "上海", "latitude": 31.2, "longitude": 121.5}],
    )
    result = execute({"function": {"name": "weather", "arguments": {"city": "上海"}}})
    assert result.startswith("上海当前天气(实时):")


def test_dispatch_unknown_city_error(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_http(monkeypatch, results=[])
    result = execute({"function": {"name": "weather", "arguments": {"city": "火星"}}})
    assert result.startswith("ERROR:")

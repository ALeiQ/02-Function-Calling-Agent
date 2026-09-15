"""Weather: dual-provider (QWeather + Open-Meteo) with HTTP layer mocked offline."""

import pytest
import requests

from src.tools import execute
from src.tools import weather as weather_mod
from src.tools.registry import ToolError
from src.tools.weather import get_weather

_OM_CURRENT = {
    "temperature_2m": 22,
    "relative_humidity_2m": 45,
    "weather_code": 0,
    "wind_speed_10m": 12,
}

_QW_NOW = {
    "temp": "18",
    "text": "多云",
    "humidity": "60",
    "windSpeed": "10",
}

_LAIYANG_OM = {"name": "Laiyang", "latitude": 36.9758, "longitude": 120.7136}
_LAIYANG_QW = {"id": "101120201", "name": "莱阳"}


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
    om_results: list[dict] | None = None,
    om_current: dict | None = None,
    qw_geo_code: str = "200",
    qw_geo: list[dict] | None = None,
    qw_now_code: str = "200",
    qw_now: dict | None = None,
    om_error: Exception | None = None,
    qw_error: Exception | None = None,
) -> list[str]:
    """Stub requests.get with per-URL payloads; returns the list of URLs hit."""
    urls: list[str] = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        urls.append(url)
        if "geoapi.qweather.com" in url:
            if qw_error:
                raise qw_error
            return FakeResponse({"code": qw_geo_code, "location": qw_geo})
        if "devapi.qweather.com" in url:
            if qw_error:
                raise qw_error
            return FakeResponse({"code": qw_now_code, "now": qw_now})
        if om_error:
            raise om_error
        if "geocoding" in url:
            return FakeResponse({"results": om_results or []})
        return FakeResponse({"current": om_current or _OM_CURRENT})

    monkeypatch.setattr(weather_mod.requests, "get", fake_get)
    return urls


def test_no_key_uses_only_openmeteo(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "")
    urls = patch_http(monkeypatch, om_results=[_LAIYANG_OM])
    result = get_weather("Laiyang")
    assert result.startswith("Laiyang当前天气")
    assert "（来源: Open-Meteo）" in result
    assert not any("qweather.com" in u for u in urls)


def test_qweather_preferred_when_both_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    patch_http(
        monkeypatch,
        om_results=[_LAIYANG_OM],
        qw_geo=[_LAIYANG_QW],
        qw_now=_QW_NOW,
    )
    result = get_weather("山东省莱阳市")
    assert result.startswith("莱阳当前天气")
    assert "多云" in result
    assert "18" in result
    assert "（来源: 和风天气）" in result


def test_openmeteo_fallback_when_qweather_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    patch_http(monkeypatch, om_results=[_LAIYANG_OM], qw_geo_code="404", qw_geo=[])
    result = get_weather("莱阳")
    assert "（来源: Open-Meteo）" in result


def test_qweather_result_win_when_openmeteo_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    patch_http(monkeypatch, om_results=[], qw_geo=[_LAIYANG_QW], qw_now=_QW_NOW)
    result = get_weather("莱阳")
    assert "（来源: 和风天气）" in result


def test_http_error_falls_back_to_other_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    patch_http(
        monkeypatch,
        om_results=[_LAIYANG_OM],
        qw_error=requests.RequestException("network down"),
    )
    result = get_weather("莱阳")
    assert "（来源: Open-Meteo）" in result


def test_both_fail_raises_combined(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "test-key")
    patch_http(
        monkeypatch,
        om_results=[],
        qw_geo_code="404",
        qw_geo=[],
        qw_now_code="404",
    )
    with pytest.raises(ToolError, match="多数据源均不可用"):
        get_weather("火星")


def test_openmeteo_normalization_strips_province_and_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "")
    seen: list[str] = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        if "geocoding" not in url:
            return FakeResponse({"current": _OM_CURRENT})
        seen.append(params["name"])
        payload = {"results": [_LAIYANG_OM]} if params["name"] == "莱阳" else {"results": []}
        return FakeResponse(payload)

    monkeypatch.setattr(weather_mod.requests, "get", fake_get)
    result = get_weather("山东省莱阳市")
    assert "（来源: Open-Meteo）" in result
    assert "莱阳" in seen
    assert "山东省莱阳市" in seen


def test_pinyin_alias_via_openmeteo(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "")
    patch_http(monkeypatch, om_results=[{"name": "北京", "latitude": 39.9, "longitude": 116.4}])
    result = get_weather("beijing")
    assert result.startswith("北京当前天气")


def test_dispatch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "")
    patch_http(monkeypatch, om_results=[{"name": "上海", "latitude": 31.2, "longitude": 121.5}])
    result = execute({"function": {"name": "weather", "arguments": {"city": "上海"}}})
    assert result.startswith("上海当前天气")


def test_dispatch_all_fail_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "qweather_api_key", "")
    patch_http(monkeypatch, om_results=[])
    result = execute({"function": {"name": "weather", "arguments": {"city": "火星"}}})
    assert result.startswith("ERROR:")

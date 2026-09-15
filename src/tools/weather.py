"""Real-time weather lookup backed by the Open-Meteo API (no API key).

The tool geocodes the city name first (``geocoding-api.open-meteo.com``), then
fetches current conditions (``api.open-meteo.com``). HTTP access is isolated in
``_geocode`` / ``_fetch_current`` so tests can replace ``requests.get``.
"""

from __future__ import annotations

import requests
from pydantic import BaseModel, Field

from src.tools.registry import ToolError, tool

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 8

# English/pinyin aliases so the model doesn't have to guess exact Chinese names.
_ALIASES = {
    "beijing": "北京",
    "bj": "北京",
    "shanghai": "上海",
    "sh": "上海",
    "shenzhen": "深圳",
    "sz": "深圳",
    "guangzhou": "广州",
    "gz": "广州",
    "hangzhou": "杭州",
    "hz": "杭州",
    "chengdu": "成都",
    "cd": "成都",
}

# WMO weather codes → Chinese conditions.
_WEATHER_CODES: dict[int, str] = {
    0: "晴",
    1: "基本晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "小雨",
    55: "中雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "雷阵雨伴强冰雹",
}


class CityNotFoundError(ToolError):
    """Raised when a city cannot be geocoded."""


class WeatherArgs(BaseModel):
    city: str = Field(..., description="城市名，支持中文（北京）或拼音（beijing）")


def _geocode(city: str) -> tuple[float, float, str]:
    """Resolve a city name to (lat, lon, localized name)."""
    resp = requests.get(
        _GEOCODING_URL,
        params={"name": city, "count": 1, "language": "zh", "format": "json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise CityNotFoundError(f"未找到城市「{city}」，请检查名称或尝试拼音")
    first = results[0]
    return first["latitude"], first["longitude"], first.get("name", city)


def _fetch_current(lat: float, lon: float) -> dict:
    """Fetch current conditions from Open-Meteo."""
    resp = requests.get(
        _FORECAST_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    current = resp.json().get("current") or {}
    if not current:
        raise ToolError("天气数据不完整，暂时无法提供该城市天气")
    return current


def get_weather(city: str) -> str:
    city = city.strip()
    key = _ALIASES.get(city.lower(), city)
    try:
        lat, lon, name = _geocode(key)
        current = _fetch_current(lat, lon)
    except requests.RequestException as exc:
        raise ToolError(f"天气服务暂时不可用: {exc}") from exc

    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    code = current.get("weather_code")
    condition = _WEATHER_CODES.get(code, f"天气代码{code}")
    return (
        f"{name}当前天气(实时): {condition}，"
        f"气温 {temp}°C，湿度 {humidity}%，"
        f"风速 {wind} km/h。"
    )


@tool(
    description=(
        "查询指定城市的实时天气（气温、天气状况、湿度、风速），使用 Open-Meteo 在线数据。"
        "当用户询问天气时使用，参数 city 支持中文或拼音。"
    ),
    args=WeatherArgs,
)
def weather(city: str) -> str:
    return get_weather(city)

"""Real-time weather via two providers: QWeather (和风天气) + Open-Meteo.

Both providers are queried concurrently; the fastest available result wins,
with QWeather preferred when both succeed (Chinese-localized descriptions).
QWeather needs a free API key (``QWEATHER_API_KEY`` in ``.env``); when the key
is missing that provider is skipped and Open-Meteo alone serves the request.
HTTP access lives in ``_qweather`` / ``_open_meteo`` so tests can replace
``requests.get``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
from pydantic import BaseModel, Field

from src.config import settings
from src.tools.registry import ToolError, tool

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_QW_GEO_URL = "https://geoapi.qweather.com/v2/city/lookup"
_QW_NOW_URL = "https://devapi.qweather.com/v7/weather/now"
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

# Chinese province/region names stripped from the front of a query.
_PROVINCES = (
    "北京市", "天津市", "上海市", "重庆市",
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省", "浙江省", "安徽省",
    "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省", "广东省", "海南省",
    "四川省", "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省",
    "内蒙古自治区", "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区",
    "香港特别行政区", "澳门特别行政区",
)

# Administrative suffixes stripped from the end of a query.
_ADMIN_SUFFIXES = (
    "自治州", "自治区", "自治县", "自治旗", "特别行政区",
    "地区", "盟", "市", "县", "区", "镇", "乡", "旗",
)

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
    """Raised when no provider can resolve a city."""


class WeatherArgs(BaseModel):
    city: str = Field(..., description="城市名，支持中文（北京/莱阳市）或拼音（beijing）")


@dataclass
class WeatherResult:
    name: str
    condition: str
    temp_c: float | None
    humidity: int | None
    wind_kmh: float | None
    source: str

    def __str__(self) -> str:
        return (
            f"{self.name}当前天气(实时): {self.condition}，"
            f"气温 {self.temp_c}°C，湿度 {self.humidity}%，"
            f"风速 {self.wind_kmh} km/h。（来源: {self.source}）"
        )


def _normalize_city(city: str) -> str:
    """Strip province prefixes and administrative suffixes (山东省莱阳市 → 莱阳)."""
    for province in sorted(_PROVINCES, key=len, reverse=True):
        if city.startswith(province):
            city = city[len(province):]
            break
    for suffix in sorted(_ADMIN_SUFFIXES, key=len, reverse=True):
        if city.endswith(suffix) and len(city) > len(suffix):
            city = city[:-len(suffix)]
    return city


def _geocode(city: str) -> tuple[float, float, str] | None:
    """Resolve a city name via Open-Meteo; None when the name is unknown."""
    resp = requests.get(
        _GEOCODING_URL,
        params={"name": city, "count": 1, "language": "zh", "format": "json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return None
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
        raise ToolError("Open-Meteo 天气数据不完整")
    return current


def _open_meteo(city: str) -> WeatherResult:
    """Open-Meteo provider: geocode candidates (original / normalized) then fetch."""
    key = _ALIASES.get(city.lower(), city)
    candidates: list[str] = []
    for cand in (key, _normalize_city(city)):
        if cand and cand not in candidates:
            candidates.append(cand)
    try:
        found = None
        for cand in candidates:
            found = _geocode(cand)
            if found:
                break
        if not found:
            raise CityNotFoundError(f"Open-Meteo 未找到城市「{city}」")
        lat, lon, name = found
        current = _fetch_current(lat, lon)
    except requests.RequestException as exc:
        raise ToolError(f"Open-Meteo 天气服务暂时不可用: {exc}") from exc

    condition = _WEATHER_CODES.get(current.get("weather_code"), "未知")
    return WeatherResult(
        name=name,
        condition=condition,
        temp_c=current.get("temperature_2m"),
        humidity=current.get("relative_humidity_2m"),
        wind_kmh=current.get("wind_speed_10m"),
        source="Open-Meteo",
    )


def _qweather(city: str) -> WeatherResult:
    """QWeather (和风天气) provider: city lookup then current conditions."""
    if not settings.qweather_api_key:
        raise ToolError("未配置和风天气 QWEATHER_API_KEY")

    lookup_city = _normalize_city(city) or city
    try:
        resp = requests.get(
            _QW_GEO_URL,
            params={"location": lookup_city, "key": settings.qweather_api_key, "number": 1},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        geo = resp.json()
        if geo.get("code") != "200" or not geo.get("location"):
            raise ToolError(f"和风天气城市检索失败(code={geo.get('code')})")
        loc = geo["location"][0]
        resp_now = requests.get(
            _QW_NOW_URL,
            params={"location": loc["id"], "key": settings.qweather_api_key},
            timeout=_TIMEOUT,
        )
        resp_now.raise_for_status()
        now = resp_now.json()
        if now.get("code") != "200" or not now.get("now"):
            raise ToolError(f"和风天气实况查询失败(code={now.get('code')})")
        data = now["now"]
    except requests.RequestException as exc:
        raise ToolError(f"和风天气服务暂时不可用: {exc}") from exc

    return WeatherResult(
        name=loc.get("name", city),
        condition=data.get("text", "未知"),
        temp_c=float(data["temp"]),
        humidity=int(float(data["humidity"])),
        wind_kmh=float(data["windSpeed"]),
        source="和风天气",
    )


def get_weather(city: str) -> str:
    """Query both providers concurrently; prefer QWeather when both succeed.

    Returns the first provider-level result in preference order (和风天气 before
    Open-Meteo); raises when every provider failed, summarizing their errors.
    """
    city = city.strip()
    jobs: list[tuple[str, Callable[[], WeatherResult]]] = []
    if settings.qweather_api_key:
        jobs.append(("和风天气", lambda: _qweather(city)))
    jobs.append(("Open-Meteo", lambda: _open_meteo(city)))

    results: dict[str, WeatherResult] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): label for label, fn in jobs}
        for future in as_completed(futures):
            label = futures[future]
            try:
                results[label] = future.result()
            except Exception as exc:
                errors.append(f"{label}: {exc}")

    for label, _ in jobs:
        if label in results:
            return str(results[label])
    hint = (
        "（提示: 配置 QWEATHER_API_KEY 可获得更好的国内县级城市支持，"
        "参见 README）"
        if not settings.qweather_api_key
        else ""
    )
    raise ToolError("天气查询失败，多数据源均不可用；" + "；".join(errors) + hint)


@tool(
    description=(
        "查询指定城市的实时天气（气温、天气状况、湿度、风速）。"
        "双数据源（和风天气 + Open-Meteo）自动择优。支持全球任意城市，"
        "参数 city 支持中文（如「莱阳市」/「山东省莱阳市」）或拼音。"
    ),
    args=WeatherArgs,
)
def weather(city: str) -> str:
    return get_weather(city)

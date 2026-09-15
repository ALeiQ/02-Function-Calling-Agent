"""Weather lookup tool backed by deterministic, offline mock data.

The mock keeps tests hermetic and results stable; the module boundary lets us
swap in a real provider (e.g. wttr.in) later without touching the agent loop.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.tools.registry import ToolError, tool

MOCK_WEATHER: dict[str, dict[str, object]] = {
    "北京": {"temp_c": 22, "condition": "晴", "humidity": 45, "wind_kmh": 12},
    "上海": {"temp_c": 26, "condition": "多云", "humidity": 70, "wind_kmh": 18},
    "深圳": {"temp_c": 30, "condition": "雷阵雨", "humidity": 82, "wind_kmh": 25},
    "广州": {"temp_c": 31, "condition": "小雨", "humidity": 78, "wind_kmh": 20},
    "杭州": {"temp_c": 24, "condition": "阴", "humidity": 65, "wind_kmh": 10},
    "成都": {"temp_c": 19, "condition": "多云", "humidity": 60, "wind_kmh": 8},
}

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


class CityNotFoundError(ToolError):
    """Raised when the requested city is not in the mock dataset."""


class WeatherArgs(BaseModel):
    city: str = Field(..., description="城市名，支持中文（北京）或拼音（beijing）")


def get_weather(city: str) -> str:
    city = city.strip()
    key = _ALIASES.get(city.lower(), city)
    data = MOCK_WEATHER.get(key)
    if not data:
        known = "、".join(MOCK_WEATHER)
        raise CityNotFoundError(f"未收录城市「{city}」，支持: {known}")
    return (
        f"{key}当前天气: {data['condition']}，"
        f"气温 {data['temp_c']}°C，湿度 {data['humidity']}%，"
        f"风速 {data['wind_kmh']} km/h。"
    )


@tool(
    description=(
        "查询指定城市的当前天气（温度、天气状况、湿度、风速）。"
        "当用户询问天气时使用，参数 city 支持中文或拼音。"
    ),
    args=WeatherArgs,
)
def weather(city: str) -> str:
    return get_weather(city)

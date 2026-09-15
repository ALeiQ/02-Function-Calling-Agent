"""Date/time tool: current date, time-of-day, weekday and timezone.

Useful for the agent to ground itself without hallucinating "today".
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.tools.registry import tool


class NowArgs(BaseModel):
    """No parameters required."""


def get_now() -> str:
    now = datetime.now().astimezone()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return (
        f"当前时间: {now:%Y-%m-%d %H:%M:%S}，"
        f"{weekdays[now.weekday()]}，时区 {now.tzinfo}。"
    )


@tool(
    description=(
        "获取当前日期、时间、星期和时区。"
        "当用户询问今天是几号、几点、星期几等时间问题时使用。"
    ),
    args=NowArgs,
)
def now() -> str:
    return get_now()

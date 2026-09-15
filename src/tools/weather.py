"""Weather lookup tool backed by deterministic, offline mock data.

The mock keeps tests hermetic and results stable; the module boundary lets us
swap in a real provider (e.g. wttr.in) later without touching the agent loop.

TODO(milestone 2): implement ``get_weather`` against mock data and expose as a tool.
"""


class CityNotFoundError(ValueError):
    """Raised when the requested city is not in the mock dataset."""
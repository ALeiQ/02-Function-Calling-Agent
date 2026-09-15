"""Weather tool tests. TODO(milestone 5): known-city + unknown-city cases."""

from src.tools.weather import CityNotFoundError


def test_city_not_found_error_type():
    assert issubclass(CityNotFoundError, ValueError)
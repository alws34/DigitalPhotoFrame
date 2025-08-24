import logging
from typing import Dict, Any

# Wrap your existing handlers behind a tiny adapter for a common interface.
from Utilities.Weather.accuweather_handler import accuweather_handler
from Utilities.Weather.open_meteo_handler import OpenMeteoWeatherHandler


class WeatherClient:
    def __init__(self, impl: Any) -> None:
        self._impl = impl

    def fetch(self) -> None:
        # Your handlers already implement a timed fetch method
        self._impl.fetch_weather_data()

    def data(self) -> Dict[str, Any]:
        # Your handlers expose get_weather_data()
        try:
            d = self._impl.get_weather_data()
            return d if isinstance(d, dict) else {}
        except Exception:
            logging.exception("weather_adapter.data() failed")
            return {}


def _has_accuweather_keys(settings: Dict[str, Any]) -> bool:
    if not isinstance(settings, dict):
        return False
    api_key = settings.get("accuweather_api_key")
    loc_key = settings.get("accuweather_location_key")
    if api_key == "YOUR_ACCUWEATHER_API_KEY" or loc_key == "YOUR_LOCATION_KEY":
        return bool(None)
    return bool(api_key and loc_key)


def build_weather_client(frame: Any, settings: Dict[str, Any]) -> WeatherClient:
    if _has_accuweather_keys(settings):
        # Mirror to legacy names that accuweather_handler expects
        settings.setdefault("weather_api_key", settings.get("accuweather_api_key", ""))
        settings.setdefault("location_key", settings.get("accuweather_location_key", ""))
        logging.info("Weather: using AccuWeather")
        return WeatherClient(accuweather_handler(frame=frame, settings=settings))

    logging.info("Weather: using Open-Meteo")
    return WeatherClient(OpenMeteoWeatherHandler(frame=frame, settings=settings))

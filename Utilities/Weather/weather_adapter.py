import logging
from typing import Dict, Any

# Wrap your existing handlers behind a tiny adapter for a common interface.
from Utilities.Weather.accuweather_handler import accuweather_handler
from Utilities.Weather.open_meteo_handler import OpenMeteoWeatherHandler


class WeatherClient:
    def __init__(self, impl: Any) -> None:
        self._impl = impl

    def fetch(self) -> None:
        self._impl.fetch_weather_data()

    def data(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            d = self._impl.get_weather_data()
            out = d if isinstance(d, dict) else {}
        except Exception:
            logging.exception("weather_adapter.data(): get_weather_data failed")
            out = {}

        # Attach icon bytes if the handler has a PIL image ready
        try:
            get_icon = getattr(self._impl, "get_weather_icon", None)
            if callable(get_icon):
                pil_img = get_icon()
                if pil_img is not None:
                    try:
                        import io
                        from PIL import Image
                        buf = io.BytesIO()
                        pil_img.convert("RGBA").save(buf, format="PNG")
                        out["icon"] = buf.getvalue()  # GUI already supports bytes
                    except Exception:
                        logging.exception("weather_adapter.data(): failed to encode PIL icon as PNG")
        except Exception:
            logging.exception("weather_adapter.data(): get_weather_icon failed")
        return out

        
    def initialize_weather_updates(self) -> None:
        # Optional: if a concrete handler provides its own scheduler, delegate to it.
        init = getattr(self._impl, "initialize_weather_updates", None)
        if callable(init):
            try:
                init()
            except Exception:
                logging.exception("weather_adapter.initialize_weather_updates() failed")

        


def _has_accuweather_keys(settings: Dict[str, Any]) -> bool:
    if not isinstance(settings, dict):
        return False
    api_key = settings.get("accuweather_api_key")
    loc_key = settings.get("accuweather_location_key")
    if api_key in (None, "", "YOUR_ACCUWEATHER_API_KEY"):
        return False
    if loc_key in (None, "", "YOUR_LOCATION_KEY"):
        return False
    return True

def build_weather_client(frame: Any, settings: Dict[str, Any]) -> WeatherClient:
    if _has_accuweather_keys(settings):
        # Mirror to legacy names that accuweather_handler expects
        settings.setdefault("weather_api_key", settings.get("accuweather_api_key", ""))
        settings.setdefault("location_key", settings.get("accuweather_location_key", ""))
        logging.info("Weather: using AccuWeather")
        return WeatherClient(accuweather_handler(frame=frame, settings=settings))

    logging.info("Weather: using Open-Meteo")
    return WeatherClient(OpenMeteoWeatherHandler(frame=frame, settings=settings))

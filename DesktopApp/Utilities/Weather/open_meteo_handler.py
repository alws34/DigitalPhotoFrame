# Handlers/open_meteo_handler.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import logging
from datetime import datetime, timedelta
import threading
from PIL import Image
import requests

from iFrame import iFrame


class OpenMeteoWeatherHandler:
    """
    Open-Meteo weather provider with AccuWeather-compatible output.
    Public API: fetch_weather_data / get_weather_data / get_weather_icon / initialize_weather_updates

    Settings (settings['open_meteo']):
      latitude, longitude  (required; explicit coords)
      units                "metric" | "imperial" (convenience)
      temperature_unit     "celsius" | "fahrenheit"
      wind_speed_unit      "kmh" | "ms" | "mph" | "kn"
      precipitation_unit   "mm" | "inch"
      timezone             "auto" | "Europe/Berlin" | ...
      timeformat           "iso8601" | "unixtime"
      cache_ttl_minutes    integer (default 60)
    """

    def __init__(self, frame: iFrame, settings):
        # settings can be a dict or a dict-like wrapper (e.g., SettingsHandler)
        self.Frame = frame
        self.weather_data = {}
        self.weather_icon = None
        self.settings = settings or {}
        self.cache_file = "openmeteo_weather_cache.json"
        self.no_weather = False

        self._http = requests.Session()
        self._http.headers.update({"User-Agent": "PhotoFrame/2.0 (+weather: open-meteo)"})

        # used by hourly fallback to pass extras back to fetch_weather_data
        self._hourly_humidity = None
        self._hourly_wind = None

    # ------------ helpers for dict-like access ------------

    @staticmethod
    def _get(obj, key, default=None):
        """
        Safe accessor for dicts and dict-like wrappers.
        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        g = getattr(obj, "get", None)
        if callable(g):
            try:
                return g(key, default)
            except TypeError:
                # some wrappers define get(self, key) without default
                try:
                    v = g(key)
                    return default if v is None else v
                except Exception:
                    return default
        # last resort: subscription
        try:
            return obj[key]
        except Exception:
            return default

    @staticmethod
    def _pick(mapping_like, *keys, default=None):
        """
        Return the first present key from a dict or dict-like object.
        Never uses 'in' on non-dicts to avoid triggering sequence protocol.
        """
        for k in keys:
            if isinstance(mapping_like, dict):
                if k in mapping_like:
                    return mapping_like[k]
                continue
            # prefer .get if available
            g = getattr(mapping_like, "get", None)
            if callable(g):
                try:
                    sentinel = object()
                    v = g(k, sentinel)
                    if v is not sentinel:
                        return v
                except TypeError:
                    try:
                        v = g(k)
                        if v is not None:
                            return v
                    except Exception:
                        pass
            # try subscription
            try:
                return mapping_like[k]
            except Exception:
                pass
        return default

    # ------------ public API ------------

    def fetch_weather_data(self):
        if self.no_weather:
            return

        cfg = self._get_cfg()
        ttl = int(self._get(cfg, "cache_ttl_minutes", 60))
        now = datetime.now()

        # 1) serve from cache if fresh and complete
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    cached = json.load(f)
                ts = cached.get("timestamp")
                cached_data = cached.get("weather_data", {}) or {}

                required = {"temp", "unit", "description", "icon", "humidity", "wind_speed"}
                cache_fresh = False
                if ts:
                    try:
                        # timestamp is naive ISO from .isoformat(); treat as local naive
                        cache_fresh = (datetime.fromisoformat(ts) + timedelta(minutes=ttl) > now)
                    except Exception:
                        cache_fresh = False
                has_required = required.issubset(set(cached_data.keys()))
                if cache_fresh and has_required:
                    self.weather_data = cached_data
                    icon_id = self.weather_data.get("icon")
                    if icon_id is not None:
                        self._fetch_icon(icon_id)
                    self.Frame.send_log_message("Using cached Open-Meteo weather.", logging.info)
                    return
                elif cache_fresh and not has_required:
                    self.Frame.send_log_message("Open-Meteo cache missing new fields; refetching.", logging.info)
        except Exception:
            # do not crash on cache errors
            pass

        # 2) resolve location (lat/lon only)
        lat, lon = self._resolve_location(cfg)
        if lat is None or lon is None:
            self.Frame.send_log_message("Open-Meteo: latitude/longitude are required in settings.", logging.error)
            self.no_weather = True
            return

        # 3) params — legacy current_weather + new-style current + hourly fallback
        current_vars = "temperature_2m,weather_code,is_day,relative_humidity_2m,wind_speed_10m"
        hourly_vars  = "temperature_2m,weather_code,is_day,relative_humidity_2m,wind_speed_10m"

        api_params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": self._get(cfg, "timezone", "auto"),
            "timeformat": self._get(cfg, "timeformat", "iso8601"),
            "current": current_vars,           # new-style current block
            "current_weather": "true",         # legacy current block
            "hourly": hourly_vars,             # fallback
            "forecast_days": 1,
        }
        # units (per docs)
        tu = self._get(cfg, "temperature_unit")
        if tu:
            api_params["temperature_unit"] = tu
        wu = self._get(cfg, "wind_speed_unit")
        if wu:
            api_params["wind_speed_unit"] = wu
        pu = self._get(cfg, "precipitation_unit")
        if pu:
            api_params["precipitation_unit"] = pu

        # 4) call API
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            self.Frame.send_log_message(f"Open-Meteo request: {url} params={api_params}", logging.info)
            r = self._http.get(url, params=api_params, timeout=15)
            r.raise_for_status()
            payload = r.json() or {}

            # Explicit API error?
            if isinstance(payload, dict) and payload.get("error"):
                self.Frame.send_log_message(f"Open-Meteo error: {payload.get('reason')}", logging.error)
                return

            # Prefer legacy block, then new 'current', else derive from 'hourly'
            temp_val, wmo, is_day = None, None, 1
            humidity = None
            wind = None

            # legacy current_weather (has no humidity)
            cw = payload.get("current_weather")
            if isinstance(cw, dict) and cw:
                temp_val = cw.get("temperature")
                wmo = cw.get("weathercode")
                is_day = 1 if cw.get("is_day", 1) else 0
                wind = cw.get("windspeed") or cw.get("wind_speed_10m")

            # new 'current' block
            if temp_val is None or wmo is None:
                cur = payload.get("current", {})
                if isinstance(cur, dict) and cur:
                    temp_val = cur.get("temperature_2m", temp_val)
                    wmo = cur.get("weather_code", wmo)
                    is_day = 1 if cur.get("is_day", is_day) else 0
                    humidity = cur.get("relative_humidity_2m", humidity)
                    wind = cur.get("wind_speed_10m", wind)

            # hourly fallback (also captures humidity/wind indices)
            if temp_val is None or wmo is None:
                self._hourly_humidity = None
                self._hourly_wind = None
                temp_val, wmo, is_day = self._from_hourly(payload)

            if humidity is None:
                humidity = getattr(self, "_hourly_humidity", None)
            if wind is None:
                wind = getattr(self, "_hourly_wind", None)

            if temp_val is None or wmo is None:
                self.Frame.send_log_message("Open-Meteo: no usable current/hourly data returned.", logging.error)
                return

            # Unit letter by requested temp unit
            temp_unit = (self._get(cfg, "temperature_unit", "celsius") or "celsius").lower()
            unit_letter = "F" if temp_unit == "fahrenheit" else "C"

            try:
                temp = round(float(temp_val))
            except Exception:
                self.Frame.send_log_message(f"Open-Meteo: bad temperature value {temp_val!r}", logging.error)
                return

            desc = self._wmo_description(wmo)
            icon_id = self._wmo_to_accuweather_icon(wmo, bool(is_day))

            self.weather_data = {
                "temp": temp,
                "unit": unit_letter,
                "description": desc,
                "icon": icon_id,
            }
            if humidity is not None:
                try:
                    self.weather_data["humidity"] = int(round(float(humidity)))
                except Exception:
                    pass
            if wind is not None:
                try:
                    self.weather_data["wind_speed"] = round(float(wind))
                except Exception:
                    self.weather_data["wind_speed"] = wind
                wind_unit = (self._get(cfg, "wind_speed_unit", "kmh") or "kmh").lower()
                if wind_unit not in ("kmh", "mph", "ms", "kn"):
                    wind_unit = "kmh"
                self.weather_data["wind_unit"] = wind_unit

            with open(self.cache_file, "w") as f:
                json.dump({"timestamp": now.isoformat(), "weather_data": self.weather_data}, f)

            if icon_id is not None:
                self._fetch_icon(icon_id)

            self.Frame.send_log_message(f"Open-Meteo parsed: {self.weather_data}", logging.info)

        except requests.RequestException as e:
            self.Frame.send_log_message(f"Open-Meteo network error: {e}", logging.error)
        except Exception as e:
            self.Frame.send_log_message(f"Open-Meteo unexpected error: {e}", logging.error)

    def get_weather_data(self):
        return self.weather_data

    def get_weather_icon(self):
        return self.weather_icon

    def initialize_weather_updates(self):
        def _loop():
            self.fetch_weather_data()
            self.stop_event = getattr(self, "stop_event", threading.Event())
            while not self.stop_event.is_set():
                self.stop_event.wait(3600)
                self.fetch_weather_data()

        self.stop_event = threading.Event()
        threading.Thread(target=_loop, daemon=True).start()

    # ------------ internals ------------

    def _get_cfg(self):
        """
        Extract and normalize the open_meteo section from settings, even when
        settings is a wrapper object.
        """
        om = {}
        if isinstance(self.settings, dict):
            om = self.settings.get("open_meteo", {}) or {}
        else:
            # dict-like wrappers
            om = self._get(self.settings, "open_meteo", {}) or {}

        # convenience: units -> specific units (do not override explicit keys)
        units = (str(self._get(om, "units", "")).lower())
        if units in ("metric", "imperial"):
            om.setdefault("temperature_unit", "fahrenheit" if units == "imperial" else "celsius")
            om.setdefault("wind_speed_unit", "mph" if units == "imperial" else "kmh")
            om.setdefault("precipitation_unit", "inch" if units == "imperial" else "mm")

        # defaults
        om.setdefault("timezone", "auto")
        om.setdefault("timeformat", "iso8601")
        om.setdefault("temperature_unit", "celsius")
        om.setdefault("wind_speed_unit", "kmh")
        om.setdefault("precipitation_unit", "mm")
        om.setdefault("cache_ttl_minutes", 60)
        return om

    def _resolve_location(self, cfg):
        """
        Returns (lat, lon) from:
        - explicit latitude/longitude in settings['open_meteo']
        - legacy top-level weather/lat/lon or settings['lat'/'lon']
        """
        lat = self._get(cfg, "latitude")
        lon = self._get(cfg, "longitude")
        try:
            if lat is not None and lon is not None:
                self.Frame.send_log_message(f"Open-Meteo: using coords ({lat}, {lon})", logging.info)
                return float(lat), float(lon)
        except Exception:
            pass
        return self._legacy_lat_lon()

    def _legacy_lat_lon(self):
        """
        Fallback for older configs:
          - settings['weather']['lat'/'lon'] or ['latitude'/'longitude']
          - settings['lat'/'lon'] or ['latitude'/'longitude'] at top level
        Works with dict-like SettingsHandler without using 'in' checks.
        """
        # Weather subsection if present
        w = {}
        if isinstance(self.settings, dict):
            w = self.settings.get("weather", {}) or {}
        else:
            w = self._get(self.settings, "weather", {}) or {}

        def pick(d, *keys):
            return self._pick(d, *keys, default=None)

        lat = pick(w, "lat", "latitude")
        lon = pick(w, "lon", "longitude")

        if lat is None or lon is None:
            # try top-level legacy keys
            lat = pick(self.settings, "lat", "latitude") if lat is None else lat
            lon = pick(self.settings, "lon", "longitude") if lon is None else lon

        try:
            if lat is not None and lon is not None:
                self.Frame.send_log_message(f"Open-Meteo: using legacy coords ({lat}, {lon})", logging.info)
            return (float(lat) if lat is not None else None,
                    float(lon) if lon is not None else None)
        except Exception:
            return None, None

    def _from_hourly(self, payload: dict):
        """Fallback: synthesize 'current' from nearest hourly record (using API utc_offset_seconds)."""
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or hourly.get("weathercode") or []
        is_day_arr = hourly.get("is_day") or []
        hums = hourly.get("relative_humidity_2m") or []
        winds = hourly.get("wind_speed_10m") or []

        if not times or not temps or not codes:
            return None, None, None

        try:
            # Compute "now" in the API's local timezone using utc_offset_seconds
            offset = int(payload.get("utc_offset_seconds", 0))
            now_local = datetime.utcnow() + timedelta(seconds=offset)
            # Round to nearest hour to match timestamps (which are hourly)
            minute = now_local.minute
            if minute >= 30:
                now_local = (now_local + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            else:
                now_local = now_local.replace(minute=0, second=0, microsecond=0)

            # Find index with minimal absolute difference
            best_idx, best_delta = 0, None
            for i, t in enumerate(times):
                try:
                    # API returns local ISO timestamps
                    dt = datetime.fromisoformat(t)
                except Exception:
                    continue
                delta = abs((dt - now_local.replace(tzinfo=None)).total_seconds())
                if best_delta is None or delta < best_delta:
                    best_idx, best_delta = i, delta

            # pick values
            temp = temps[best_idx] if best_idx < len(temps) else None
            wmo = codes[best_idx] if best_idx < len(codes) else None
            is_day = is_day_arr[best_idx] if best_idx < len(is_day_arr) else 1

            # stash extras so caller can use them
            self._hourly_humidity = hums[best_idx] if best_idx < len(hums) else None
            self._hourly_wind = winds[best_idx] if best_idx < len(winds) else None

            return temp, wmo, is_day
        except Exception:
            return None, None, None

    def _fetch_icon(self, icon_type: int):
        try:
            url = f"https://developer.accuweather.com/sites/default/files/{icon_type:02d}-s.png"
            self.Frame.send_log_message(f"Fetching weather icon: {url}", logging.info)
            resp = self._http.get(url, stream=True, timeout=10)
            resp.raise_for_status()
            self.weather_icon = Image.open(resp.raw)
        except Exception as e:
            self.Frame.send_log_message(f"Open-Meteo icon fetch failed: {e}", logging.warning)
            self.weather_icon = None

    def _wmo_description(self, code: int) -> str:
        desc = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            56: "Light freezing drizzle", 57: "Dense freezing drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            66: "Light freezing rain", 67: "Heavy freezing rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
            80: "Rain showers", 81: "Heavy rain showers", 82: "Violent rain showers",
            85: "Snow showers", 86: "Heavy snow showers",
            95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
        }
        try:
            return desc.get(int(code), "Unknown")
        except Exception:
            return "Unknown"

    def _wmo_to_accuweather_icon(self, code: int, is_day: bool) -> int:
        code = int(code)
        day = bool(is_day)
        if code == 0:   return 1 if day else 33
        if code == 1:   return 2 if day else 34
        if code == 2:   return 3 if day else 35
        if code == 3:   return 7
        if code in (45, 48): return 11
        if code in (51, 53, 55): return 18
        if code in (56, 57, 66, 67): return 26
        if code in (61, 63, 65): return 18
        if code in (80, 81, 82): return 14 if day else 39
        if code in (71, 73, 75, 77): return 22
        if code in (85, 86): return 19
        if code in (95, 96, 99): return 15 if day else 41
        return 7

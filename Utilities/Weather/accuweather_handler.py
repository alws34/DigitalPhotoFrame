import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import logging
import os
from datetime import datetime, timedelta
import threading
from PIL import Image
import requests
from iFrame import iFrame

class accuweather_handler():

    def __init__(self, frame: iFrame, settings: dict):
        self.Frame = frame
        self.weather_data = {}
        self.weather_icon = None
        self.settings = settings
        self.cache_file = "weather_cache.json"
        self.no_weather = False
        
    def fetch_weather_icon(self, icon_type):
        try:
            icon_url = f"https://developer.accuweather.com/sites/default/files/{icon_type:02d}-s.png"
            self.Frame.send_log_message(f"Fetching weather icon from: {icon_url}", logging.info)
            icon_response = requests.get(icon_url, stream=True)
            icon_response.raise_for_status()
            self.weather_icon = Image.open(icon_response.raw)
            self.Frame.send_log_message("Weather icon successfully fetched.", logging.info)
        except Exception as e:
            self.Frame.send_log_message(f"Weather icon could not be fetched: {e}. Falling back to text-only rendering.", logging.warning)
            self.weather_icon = None
        if not self.weather_icon:
            logging.warning("Weather icon unavailable. Skipping weather icon rendering.")
        
    def fetch_weather_data(self):
        """Fetch current weather data from AccuWeather API, limited to once per hour."""
        if self.no_weather:
            return
        
        try:
            # Check if a valid cached weather file exists
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as file:
                    cached_data = json.load(file)
                    cache_time = datetime.fromisoformat(cached_data.get("timestamp", ""))
                    if cache_time + timedelta(hours=1) > datetime.now():
                        self.weather_data = cached_data.get("weather_data", {})
                        if not self.weather_data:
                            self.Frame.send_log_message("Cached weather data is empty.", logging.error)
                            return
                        self.fetch_weather_icon(icon_type=self.weather_data['icon'])
                        self.Frame.send_log_message(f"Using cached weather data: {self.weather_data}", logging.info)
                        return

            
            self.Frame.send_log_message("Fetching weather data...", logging.info)

            # Retrieve API key and location key from settings
            api_key = self.settings.get("accuweather_api_key", "")
            location_key = self.settings.get("accuweather_location_key", "")

            if not api_key or not location_key:
                self.Frame.send_log_message("AccuWeather API key or location key is missing.", logging.error)
                self.no_weather = True
                return

            # Build the API URL
            url = f"http://dataservice.accuweather.com/currentconditions/v1/{location_key}?apikey={api_key}"
            #self.Frame.send_log_message(f"Making request to AccuWeather: {url}", logging.info)

            # Perform the API call
            response = requests.get(url)
            response.raise_for_status()
            self.Frame.send_log_message(f"Weather API response: {response.text}", logging.info)

            # Parse the JSON response
            data = response.json()
            if not data or len(data) == 0:
                self.Frame.send_log_message("Weather API response is empty or invalid.", logging.error)
                return

            # Extract weather details
            data = data[0]
            self.weather_data = {
                "temp": round(data["Temperature"]["Metric"]["Value"]),
                "unit": data["Temperature"]["Metric"]["Unit"],
                "description": data["WeatherText"],
                "icon": data["WeatherIcon"]
            }
            self.Frame.send_log_message(f"Parsed weather data: {self.weather_data}", logging.info)
            if not self.weather_data:
                logging.warning("Weather data unavailable. Skipping weather rendering.")

            # Save weather data to cache
            with open(self.cache_file, "w") as file:
                json.dump({"timestamp": datetime.now().isoformat(), "weather_data": self.weather_data}, file)
                self.Frame.send_log_message("Weather data cached successfully.", logging.info)

            # Fetch the weather icon
            self.fetch_weather_icon(icon_type=self.weather_data['icon'])
        except requests.exceptions.RequestException as e:
            self.Frame.send_log_message(f"Error fetching weather data: {e}", logging.error)
        except Exception as e:
            self.Frame.send_log_message(f"Unexpected error: {e}", logging.error)

    def get_weather_data(self):
        return self.weather_data

    def get_weather_icon(self):
        return self.weather_icon

    def initialize_weather_updates(self):
        """Fetch weather data immediately and then set up periodic updates."""
        def update_weather_periodically():
            self.fetch_weather_data()
            while not self.stop_event.is_set():
                self.stop_event.wait(3600)
                self.fetch_weather_data()

        self.stop_event = threading.Event()
        weather_thread = threading.Thread(target=update_weather_periodically, daemon=True)
        weather_thread.start()

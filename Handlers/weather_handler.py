
import logging
import threading
import requests
import time
from PIL import Image, ImageDraw, ImageFont
from cv2 import COLOR_BGR2RGB, COLOR_RGB2BGR, cvtColor

class weather_handler():
    from iFrame import iFrame
    def __init__(self, frame:iFrame, settings:dict):
        self.Frame = frame 
        self.weather_data = {}
        self.weather_icon = None
        self.settings = settings

    def fetch_weather_data(self):
        """Fetch current weather data from AccuWeather API, limited to once per hour."""
        try:
            # Check if enough time has passed to make a new API call
            current_time = time.time()
            if hasattr(self, 'next_weather_update') and current_time < self.next_weather_update:
                #self.Frame.logger.info("Weather update skipped: waiting for next allowed time.")
                return
            
            self.Frame.send_log_message("Fetching weather data...",logging.info)

            # Retrieve API key and location key from settings
            api_key = self.settings.get("weather_api_key", "")
            location_key = self.settings.get("location_key", "")

            if not api_key or not location_key:
                self.Frame.send_log_message("AccuWeather API key or location key is missing.",logging.error)
                return

            # Build the API URL
            url = f"http://dataservice.accuweather.com/currentconditions/v1/{location_key}?apikey={api_key}"
            self.Frame.send_log_message(f"Making request to AccuWeather: {url}",logging.info)
            # Perform the API call
            response = requests.get(url)
            response.raise_for_status()
            self.Frame.send_log_message(f"Weather API response: {response.text}",logging.info)

            # Parse the JSON response
            data = response.json()
            if not data or len(data) == 0:
                self.Frame.send_log_message("Weather API response is empty or invalid.",logging.error)
                return

            # Extract weather details
            data = data[0]
            self.weather_data = {
                "temp": round(data["Temperature"]["Metric"]["Value"]),
                "unit": data["Temperature"]["Metric"]["Unit"],
                "description": data["WeatherText"],
                "icon": data["WeatherIcon"]
            }
            self.Frame.send_log_message(f"Parsed weather data: {self.weather_data}",logging.info)

            # Fetch the weather icon
            try:
                icon_url = f"https://developer.accuweather.com/sites/default/files/{self.weather_data['icon']:02d}-s.png"
                self.Frame.logger.info(f"Fetching weather icon from: {icon_url}")
                icon_response = requests.get(icon_url, stream=True)
                icon_response.raise_for_status()
                self.weather_icon = Image.open(icon_response.raw)
                self.Frame.send_log_message("Weather icon successfully fetched.",logging.info)
            except Exception as e:
                self.Frame.send_log_message(f"Weather icon could not be fetched: {e}. Falling back to text-only rendering.",logging.warning)
                self.weather_icon = None

            # Set the next allowable update time (1 hour later)
            self.next_weather_update = current_time + 3600  # 1 hour = 3600 seconds

        except requests.exceptions.RequestException as e:
            self.Frame.send_log_message(f"Error fetching weather data: {e}",logging.error)
        except Exception as e:
            self.Frame.send_log_message(f"Unexpected error: {e}",logging.error)

        def initialize_weather_updates(self):
            """Initialize periodic weather updates every hour."""
            def update_weather_periodically():
                # Fetch weather data immediately on startup
                self.fetch_weather_data()

                while not self.stop_event.is_set():
                    # Wait for 1 hour or until stop event
                    self.stop_event.wait(3600)
                    self.fetch_weather_data()

            self.stop_event = threading.Event()
            weather_thread = threading.Thread(target=update_weather_periodically, daemon=True)
            weather_thread.start()

    def get_weather_data(self):
        return self.weather_data
    def get_weather_icon(self):
        return self.weather_icon
        
    def initialize_weather_updates(self):
        """Fetch weather data immediately and then set up periodic updates."""
        def update_weather_periodically():
            # Fetch weather data immediately when the app starts
            self.fetch_weather_data()

            while not self.stop_event.is_set():
                # Wait for 1 hour or until the event is set
                self.stop_event.wait(3600)
                self.fetch_weather_data()

        self.stop_event = threading.Event()
        weather_thread = threading.Thread(target=update_weather_periodically, daemon=True)
        weather_thread.start()

    #endregion Weather
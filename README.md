# Digital Photo Frame V2.0

A Python-based photo frame application for Raspberry Pi, offering beautiful image transitions, real-time weather updates, and live video streaming capabilities.

## Features

- **Image Transitions:**
  - Alpha Dissolve
  - Pixel Dissolve
  - Checkerboard
  - Blinds
  - Scroll
  - Wipe
  - Zoom Out
  - Zoom In
  - Iris Open
  - Iris Close
  - Barn Door Open
  - Barn Door Close
  - Shrink
  - Stretch

- **Real-Time Weather Updates:**
  - Displays current temperature, weather description, and an icon overlay.
  - Fetches weather data from the AccuWeather API.

- **Dynamic Image Resizing:**
  - Resizes images to fit the screen while maintaining the aspect ratio.
  - Blurred, translucent backgrounds for a professional look.

- **Directory Monitoring:**
  - Automatically detects changes in the `Images/` directory and reloads images.

- **MJPEG Server:**
  - Streams the current photo frame view via a local web server for easy remote access.

## Installation

Follow these steps to set up the project on your Raspberry Pi:

### Prerequisites

1. Ensure Raspberry Pi OS is installed.
2. Install Docker and Docker Compose:
`   sudo apt update
   sudo apt install docker.io docker-compose -y`

### Raspberry Pi Configuration
Install xscreensaver and disable it:

`sudo apt install xscreensaver -y`

After installing, change the screensaver to blank (disable it) - you may disable screen blanking in any other way you see fit. 


### Edit the Raspberry Pi's boot configuration:
```sudo nano /boot/firmware/config.txt```
Change:
`dtoverlay=vc4-kms-v3d`
To:
`dtoverlay=vc4-fkms-v3d`

Reboot the Raspberry Pi:
`sudo reboot`

## Setting Up the Application
Clone the repository:

`git clone https://github.com/alws34/DigitalPhotoFrame2`
`cd DigitalPhotoFrame2`

- Place your images in the Images/ directory.

Create a settings.json file in the root directory with the required configuration
* Example Configuration:
```  
{
    "font_name": "arial.ttf",
    "time_font_size": 60,
    "date_font_size": 30,
    "margin_left": 80,
    "margin_bottom": 50,
    "margin_right": 50,
    "spacing_between": 50,
    "animation_duration": 10,
    "delay_between_images": 30,
    "allow_translucent_background": true,
    "weather_api_key": "<YOUR_API_KEY>",  //Accuweather API
    "location_key": "<YOUR_LOCATION_KEY>" //Accuweather API
    "mjpeg_server":{
        "allow_mjpeg_server": true,
        "server_port": 5001,
        "host": "0.0.0.0"
    }
}
```


### Build and run the application with Docker:

`docker-compose up --build`

If the container doesnt work (getting error: `_tkinter.TclError: couldn't connect to display ":0"`)
run the following commands: 
`sudo nano ~/.bashrc`
Add at the END of the file: 
`xhost +local:`
`export DISPLAY=:0`
Run: 
`source ~/.bashrc`
`xhost`
`sudo reboot`


## Usage
Access the photo frame interface directly on the Raspberry Pi or through the web server at:

`http://<raspberry_pi_ip>:5001/video_feed`

To add new images, place them in the Images/ directory. The application automatically detects and reloads the new images.

Customize the transition effects or weather API settings by modifying the settings.json file.

Contribution
Feel free to submit issues, fork the repository, and make pull requests. Contributions are welcome to enhance features or fix bugs.

License
This project is licensed under the MIT License. See the LICENSE file for details.

# PhotoFrame

This Java program displays a digital photo frame on your computer screen. It transitions between photos using various animation effects and displays the current date and time.

## Features

- Displays photos in a fullscreen window
- Transitions between photos with various animation effects
- Shows the current date and time
- Supports various image formats (JPG, PNG, JPEG, HEIC, HEIF)
- Customizable settings through a JSON file (animations, date/time format, image folder path)

## Requirements

Java Runtime Environment (JRE)

### Running the program:

Download the source code  or the latest [Release](https://github.com/alws34/DigitalPhotoFrame/releases) and ensure you have Java installed.

- (Optional) Edit the settings.json file to customize animation effects, date/time format, and image folder path etc.
Compile the source code using a Java compiler (e.g., javac PhotoFrame.java).
Run the program using the command java PhotoFrame.
- the project was copiled using Intellij CE, with JDK20. 

## Customization:

You can modify the AppSettings class to define available animation effects and their default values.
Edit the settings.json file to choose your preferred animation effect, date/time format, and image folder path.



    "colorHex": "#D5C0FF", //Hex only
    "FontName": "Arial", // make sure you have the desired font installed
    "ImagesPath": null, //if null, than the resources directory must be in the same directory as the .jar file
    "DateFormat": "dd/MM/yyyy", 
    "TimeFormat": "HH:mm:ss", //use hh for 12 hr. you may want to use "hh:mm:ss aa" to also display am/pm
    "DelayBetweenImages":35000, //35 seconds in milliseconds
    "DefaultMaxFPS":30,
    "DefaultAnimationDuration":5000, // 5 seconds in milliseconds
	"DefaultVerticalImageEffect": 3 // can be 1 to 3 - 1 and 2 are CPU intensive*.

## Note
- This is a basic implementation and can be extended with additional features like playlists, image scaling options, and more.
- This is meant to run on  a Raspberry pi 4 with at least 2 gb of ram.
- This will not run a raspberry pi 3 or below (including raspberry pi zero)


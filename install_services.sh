#!/bin/bash

# Define service file paths
SERVICES_DIR="/etc/systemd/system"
PHOTOF_RAME_SERVICE="PhotoFrame.service"
SCREEN_CONTROL_SERVICE="ScreenControl.service"
STATS_MONITOR_SERVICE="StatsMonitor.service"
FLASK_APP_SERVICE="FlaskApp.service"

# Content for PhotoFrame.service
PHOTOF_RAME_CONTENT="[Unit]
Description=PhotoFrame Python Script
After=graphical.target

[Service]
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash -c \"source /home/pi/Desktop/DigitalPhotoFrame/env/bin/activate && python3 /home/pi/Desktop/DigitalPhotoFrame/PhotoFrame.py\"
WorkingDirectory=/home/pi/Desktop/DigitalPhotoFrame
Restart=always
RestartSec=5
User=pi
StandardOutput=journal
StandardError=journal
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical.target"

# Content for FlaskApp.service
FLASK_APP_CONTENT="[Unit]
Description=Flask Application
After=network.target

[Service]
ExecStart=/bin/bash -c \"source /home/pi/Desktop/DigitalPhotoFrame/env/bin/activate && python3 /home/pi/Desktop/DigitalPhotoFrame/main.py\"
WorkingDirectory=/home/pi/Desktop/DigitalPhotoFrame
Restart=always
RestartSec=5
User=pi
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target"

# Function to create and enable a service
create_and_enable_service() {
    local service_name=$1
    local service_content=$2

    echo "Creating $service_name..."
    echo "$service_content" | sudo tee "$SERVICES_DIR/$service_name" > /dev/null

    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    echo "Enabling $service_name..."
    sudo systemctl enable "$service_name"

    echo "Starting $service_name..."
    sudo systemctl start "$service_name"

    echo "$service_name installed and started successfully!"
}

# Create and enable the services
create_and_enable_service "$PHOTOF_RAME_SERVICE" "$PHOTOF_RAME_CONTENT"
create_and_enable_service "$FLASK_APP_SERVICE" "$FLASK_APP_CONTENT"

echo "All services installed and started successfully!"

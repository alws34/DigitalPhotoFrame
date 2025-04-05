FROM python:3.11-slim

# Install dependencies for tkinter and fonts
RUN apt-get update && apt-get install -y \
    python3-tk \
    libjpeg-dev \
    libfreetype6-dev \
    ttf-dejavu \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

# Create venv manually
RUN python3 -m venv env \
    && . env/bin/activate \
    && pip install --upgrade pip \
    && pip install -r Requirments.txt

CMD [ "env/bin/python", "PhotoFrameDesktopApp.py" ]

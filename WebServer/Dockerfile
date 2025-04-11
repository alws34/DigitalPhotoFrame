FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    libgl1-mesa-glx \
    libglib2.0-0 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY WebServer/ /app/
COPY Handlers/ /app/Handlers/
COPY Utilities/ /app/Utilities/
COPY Effects/ /app/Effects/

RUN mkdir -p /app/Images

RUN pip install --no-cache-dir -r Requirments.txt

EXPOSE 5001

CMD ["python", "PhotoFrameServer.py"]

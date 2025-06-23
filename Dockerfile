# Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt
 
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1          \  # libGL.so.1 provider
        libglib2.0-0    \  # needed by cv2 for image codecs
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p WebServer/Images

EXPOSE 5001

CMD ["python", "WebServer/PhotoFrameServer.py"]

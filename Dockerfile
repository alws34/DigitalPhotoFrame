# Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p WebServer/Images

EXPOSE 5001

CMD ["python", "WebServer/PhotoFrameServer.py"]

FROM python:3.10-slim

WORKDIR /app

COPY ./app
RUN mkdir -p /app/WebServer/Images 

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python", "WebServer/PhotoFrameServer.py"]


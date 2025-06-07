# ---- build stage ----------------------------------------------------------
FROM python:3.11-slim

# Update and upgrade system packages to address vulnerabilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \       
        libgl1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install Python deps first for layer-caching
COPY Requirments.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# bring in the rest of the source tree
COPY . /app

EXPOSE 5001
CMD ["python", "-m", "WebServer/PhotoFrameServer"]

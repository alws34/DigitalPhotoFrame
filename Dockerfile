# Base image
FROM python:3.9-slim

# Set environment variables to suppress Tkinter's GUI warnings
ENV DEBIAN_FRONTEND=noninteractive

# Install Tkinter and other dependencies
RUN apt-get update && apt-get install -y \
    python3-tk \
    tk-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libz-dev \
    libopencv-dev \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy application files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r Requirments.txt

# Expose necessary ports
EXPOSE 5000 5001

# Default command (to be overridden in docker-compose.yml)
CMD ["bash"]

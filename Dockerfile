FROM python:3.10-slim

# Set working dir
WORKDIR /app

# Avoid dragging in .git, pyc files, etc.
#COPY .dockerignore /app/.dockerignore
COPY ./app
# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Expose the port your Flask app listens on
EXPOSE 5000

# Default command: run your photoframe script
CMD ["python", "WebServer/PhotoFrameServer.py"]


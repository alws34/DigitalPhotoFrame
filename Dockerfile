# ==============================================================================
# DigitalPhotoFrame — 4-Stage Multi-Stage Dockerfile
#
# WHY BYTECODE-ONLY WORKS IN PYTHON 3.11:
#   CPython has always been able to import .pyc files placed directly alongside
#   where the corresponding .py would live. When a .py is absent and a .pyc
#   exists at the same path (e.g. app.pyc next to where app.py would be),
#   Python 3.11+ will discover and execute the .pyc via its import machinery.
#   `compileall -b` generates exactly this layout: foo.pyc sits next to foo.py.
#   After deleting all .py files only .pyc files remain. Python finds and runs
#   them normally. This removes all human-readable source from the runtime
#   image while preserving full functionality, shrinks layer size, and prevents
#   inadvertent source disclosure in production deployments.
# ==============================================================================


# ==============================================================================
# Stage 1: frontend-builder — compile the React/Vite admin UI
# ==============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend

# Install deps before copying source for better layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy source and build; output lands in /build/frontend/dist/
COPY frontend/ ./
RUN npm run build


# ==============================================================================
# Stage 2: python-deps — install Python packages into an isolated prefix
# ==============================================================================
FROM python:3.11-slim AS python-deps

# Build-time system libraries required to compile native extensions
# (libheif-dev for pillow-heif, libffi-dev for cryptography/argon2-cffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libheif-dev \
    libde265-dev \
    libjpeg62-turbo-dev \
    libopenjp2-7-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt /tmp/requirements-docker.txt

# Install into /install so we can COPY the prefix cleanly into the final stage.
# --no-cache-dir keeps this layer as small as possible.
RUN pip install --no-cache-dir \
    --prefix=/install \
    -r /tmp/requirements-docker.txt


# ==============================================================================
# Stage 3: bytecode-compiler — compile source to .pyc, then delete all .py
# ==============================================================================
FROM python:3.11-slim AS bytecode-compiler

WORKDIR /app

# Copy only the application Python source that belongs in the runtime image.
# Excluded: env/, Tests/, docs/, .claude/, frontend/src/, *.egg-info/,
#           metadata.json, photoframe_settings.json (mounted as volumes).
# config.py has been deleted — intentionally not listed here.
COPY app.py app_modes.py logging_setup.py pyproject.toml ./
COPY FrameServer/ ./FrameServer/
COPY FrameGUI/   ./FrameGUI/
COPY WebAPI/     ./WebAPI/
COPY Utilities/  ./Utilities/

# 1. Compile every .py to a .pyc alongside it (-b = beside-source layout).
#    compileall exits 0 even for files with syntax warnings; -q suppresses noise.
# 2. Remove all .py source files.
# 3. Remove any residual __pycache__ directories (compileall -b does not create
#    them, but defensive cleanup prevents any stray ones from prior COPY layers).
RUN python -m compileall -b -q . \
    && find . -name "*.py" -delete \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; true


# ==============================================================================
# Stage 4: runtime — final image, NO .py source files
# ==============================================================================
FROM python:3.11-slim

LABEL maintainer="DigitalPhotoFrame"
LABEL description="Digital Photo Frame — Flask backend + pygame display (bytecode-only runtime)"

# Runtime system libraries.  Build-time headers (-dev packages) are NOT copied.
# libheif1 + libde265-0: HEIC/HEIF decoding via pillow-heif
# libsdl2-*: pygame display and input (needed for --display pygame mode)
# libgl1 + mesa libs: OpenGL/EGL for hardware-accelerated rendering on Pi
# network-manager + wireless-tools: nmcli Wi-Fi management from the API
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libjpeg62-turbo \
    libopenjp2-7 \
    libheif1 \
    libde265-0 \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    libwayland-client0 \
    libwayland-egl1 \
    libwayland-cursor0 \
    libxkbcommon0 \
    libegl1 \
    libegl-mesa0 \
    libgles2 \
    libgbm1 \
    curl \
    network-manager \
    wireless-tools \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python packages (from python-deps stage) --------------------------------
# The /install prefix matches python:3.11-slim's site-packages layout.
# Copying to / merges lib/python3.11/site-packages/ into the system Python.
COPY --from=python-deps /install/ /usr/local/

# --- Bytecode-only application (from bytecode-compiler stage) ----------------
# Only .pyc files are present; no .py source files enter this stage.
COPY --from=bytecode-compiler /app/ /app/

# --- Built frontend (from frontend-builder stage) ----------------------------
COPY --from=frontend-builder /build/frontend/dist /app/frontend/dist

# --- Static assets (non-Python, non-source) ----------------------------------
COPY arial.ttf /app/arial.ttf
COPY assets/   /app/assets/

# --- WebAPI bundled static files (heic2any.min.js, vendor/) ------------------
# These are already inside /app/WebAPI/static/ via the bytecode-compiler COPY,
# since compileall only touches .py → .pyc and leaves other files intact.

# Runtime data directories; actual data mounted as volumes at runtime
RUN mkdir -p /app/Images /data \
    && chown -R 1000:1000 /app /data

ENV PF_DB_PATH=/data/photoframe.db

# Images directory and persistent DB are always volumes.
# photoframe_settings.json and metadata.json are injected via compose volumes.
VOLUME ["/app/Images", "/data"]

# Simple liveness probe: Flask must respond on the configured port
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:5002/ || exit 1

# Non-root user (matches host pi UID 1000)
USER 1000:1000

# Default: pygame display mode.
# Override to --headless for server-only / Pi headless deployments.
ENTRYPOINT ["python", "app.py"]
CMD ["--display", "pygame"]

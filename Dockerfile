# =============================================================================
# Crypt-Master Dockerfile
# Multi-stage build for ARM64 deployment (EC2 t4g.small)
# Target: AWS ECR (138120257234.dkr.ecr.eu-west-3.amazonaws.com)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and compile TA-Lib
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install build dependencies for TA-Lib and other native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    autoconf \
    automake \
    libtool \
    && rm -rf /var/lib/apt/lists/*

# Install TA-Lib C library from source (required for ta-lib Python package)
# Note: We run autoreconf to regenerate config files for ARM64 compatibility
# Using single-threaded make to avoid race conditions in the build
ARG TALIB_VERSION=0.4.0
RUN wget -q https://github.com/ta-lib/ta-lib/releases/download/v${TALIB_VERSION}/ta-lib-${TALIB_VERSION}-src.tar.gz \
    && tar -xzf ta-lib-${TALIB_VERSION}-src.tar.gz \
    && cd ta-lib \
    && autoreconf -fi \
    && ./configure --prefix=/usr/local \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-${TALIB_VERSION}-src.tar.gz

# Update library cache
RUN ldconfig

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files and README first for better layer caching
# README.md is required by pyproject.toml
COPY pyproject.toml uv.lock README.md ./

# Install Python dependencies using uv
# Using --frozen to ensure reproducible builds from lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY config/ ./config/
COPY apps/ ./apps/
COPY agents/ ./agents/
COPY lib/ ./lib/
COPY templates/ ./templates/
COPY static/ ./static/
COPY manage.py ./

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# -----------------------------------------------------------------------------
# Stage 2: Runtime - Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# Labels for image metadata
LABEL maintainer="Crypt-Master Team" \
    description="Pionex Trading Bot - Automated cryptocurrency trading system" \
    version="0.1.0" \
    org.opencontainers.image.source="https://github.com/your-org/crypt-master"

# Set environment variables for Python runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    # Application settings
    APP_HOME=/app \
    # Gunicorn settings
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=2 \
    GUNICORN_TIMEOUT=120 \
    GUNICORN_KEEPALIVE=5 \
    # Django settings
    DJANGO_SETTINGS_MODULE=config.settings

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required for psycopg PostgreSQL driver
    libpq5 \
    # Required for healthchecks
    curl \
    # Required for TA-Lib runtime
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy TA-Lib shared libraries from builder
COPY --from=builder /usr/local/lib/libta_lib* /usr/local/lib/
RUN ldconfig

# Create non-root user for security
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR ${APP_HOME}

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code from builder
COPY --from=builder /app/config ./config
COPY --from=builder /app/apps ./apps
COPY --from=builder /app/agents ./agents
COPY --from=builder /app/lib ./lib
COPY --from=builder /app/templates ./templates
COPY --from=builder /app/static ./static
COPY --from=builder /app/manage.py ./

# Create directories for logs and static files
RUN mkdir -p /app/logs /app/staticfiles /app/celerybeat \
    && chown -R appuser:appgroup /app

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

# Collect static files (will be overwritten at runtime if needed)
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Expose port for web service
EXPOSE 8000

# Health check for web service
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Default command - can be overridden in docker-compose.yml
CMD ["gunicorn", "config.wsgi:application", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "2", \
    "--threads", "2", \
    "--timeout", "120", \
    "--keep-alive", "5", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--capture-output", \
    "--enable-stdio-inheritance"]

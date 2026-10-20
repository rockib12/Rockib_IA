# =========================================================
# ROCKIB AI — ALL-IN-ONE PRODUCTION DOCKERFILE
# Front (React/Vite) + Back (FastAPI) + Nginx (Reverse Proxy)
# =========================================================

# ---------------------------------------------------------
# STAGE 1: Frontend Builder (React + Vite)
# ---------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy npm dependencies definition
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source and build static production assets
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------
# STAGE 2: Backend Dependencies Builder (Python + Poetry)
# ---------------------------------------------------------
FROM python:3.11-slim AS backend-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry

# Copy dependency definition files
COPY pyproject.toml poetry.lock ./

# Install python dependencies in system environment
RUN poetry config virtualenvs.create false \
    && poetry lock \
    && poetry install --no-root --only main



# ---------------------------------------------------------
# STAGE 3: Final Unified Runtime (Front + Back + Nginx)
# ---------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Install system runtime packages: Nginx, Supervisor, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies and executables from backend-builder
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy compiled frontend static assets from frontend-builder
COPY --from=frontend-builder /app/frontend/dist /var/www/html

# Copy backend source code and configurations
COPY app /app/app
COPY alembic.ini /app/
COPY pyproject.toml /app/

# Configure Nginx
COPY nginx.conf /etc/nginx/conf.d/rockib.conf
RUN rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf

# Configure Supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Configure Entrypoint script (fix CRLF if edited on Windows)
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# Create non-privileged runtime user for Celery & workspace sandboxing
RUN useradd -m -u 10001 -s /bin/sh rockib \
    && mkdir -p /tmp/rockib_workspaces \
    && chown -R rockib:rockib /app /tmp/rockib_workspaces

# Expose ports: 80 (Nginx web & reverse proxy), 8000 (direct FastAPI backend)
EXPOSE 80 8000

# Deep healthcheck testing real availability of FastAPI, PostgreSQL and Redis via Nginx
HEALTHCHECK --interval=20s --timeout=5s --retries=3 \
    CMD curl -f http://localhost/api/v1/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

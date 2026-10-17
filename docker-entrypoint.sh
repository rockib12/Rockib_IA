#!/bin/sh
set -e

# Run database migrations if database URL is configured
if [ -n "$DATABASE_URL" ] || [ -n "$ASYNC_DATABASE_URL" ]; then
    echo "==> [Entrypoint] Verifying database connection & applying Alembic migrations..."
    alembic upgrade head || echo "==> [Entrypoint] Notice: Alembic migration skipped or database not reachable yet."
fi

echo "==> [Entrypoint] Starting Rockib AI all-in-one container (Backend + Frontend + Nginx)..."
exec "$@"

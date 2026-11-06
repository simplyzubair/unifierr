#!/bin/sh
set -e

# Run database schema migrations
echo "Running database migrations..."
alembic upgrade head

# Launch Unifierr application server
echo "Starting Unifierr server on port 8484..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8484

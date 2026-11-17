#!/usr/bin/env bash
# Run a Django management command with the project's venv.
# Usage: ./run_manage.sh funds_daily --weekday 0
set -euo pipefail
APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
VENV="${VENV:-$APP_DIR/venv}"
cd "$APP_DIR/backend"
exec "$VENV/bin/python" manage.py "$@"
